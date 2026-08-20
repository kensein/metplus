import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import branca.colormap as cm
from matplotlib import colors as colors
# import matplotlib.pyplot as plt
import os
# os.environ["HOST"] = "0.0.0.0"
# os.environ["LOCAL_TILESERVER"] = "false"
# os.environ["MAPTILER_KEY"] = "1MjRO8lKRhwmZbWI6s9o"
# import leafmap.maplibregl as leafmap
import leafmap.foliumap as leafmap
# import leafmap.kepler as leafmap
import folium
from streamlit_folium import st_folium, folium_static
# import os
import rioxarray
import xarray as xr
# import matplotlib.colors as mcolors
# from matplotlib.colors import ListedColormap
# import plotly.express as px
# import tempfile
import rasterio
# os.environ['LOCALTILESERVER_CLIENT_PREFIX'] = 'proxy/{port}'
	
st.set_page_config(page_title='Dashboard', layout='wide')

# st.title('Future Scenarios Dashboard')

st.sidebar.title('About')
st.sidebar.info('Explore the Future Scenarios')

### FUNCTIONS
count_vars = ['PHE']
max_vars = ['TXx']
min_vars = ['TNn']
mean_vars = ['TMean', 'TX90p', 'TN90p']

def aggregate(da, mode, var):
    """
    Compute climatological annual/seasonal statistics.

    TMean, TX90p, TN90p:
        monthly means -> annual/seasonal mean -> climatological mean
    TXx:
        monthly max values -> annual/seasonal maximum -> climatological mean
    TNn:
        monthly min values -> annual/seasonal minimum -> climatological mean
    PHE:
        monthly counts -> annual/seasonal total -> climatological mean
    """

    if var in count_vars:
        op = 'sum'
    elif var in max_vars:
        op = 'max'
    elif var in min_vars:
        op = 'min'
    else:
        op = 'mean'

    def apply_op(x):
        if op == 'sum':
            return x.sum('time')
        elif op == 'max':
            return x.max('time')
        elif op == 'min':
            return x.min('time')
        else:
            return x.mean('time')

    # Annual climatology
    if mode == 'ANNUAL':
        yearly = (da.groupby('time.year').map(apply_op))
        return yearly.mean('year')

    # Seasonal climatology
    season_da = da.where(da.time.dt.season == mode, drop=True)

    # Handle DJF correctly (Dec belongs to next year)
    if mode == 'DJF':
        season_year = xr.where(season_da.time.dt.month == 12,
                               season_da.time.dt.year + 1,
                               season_da.time.dt.year)

        season_da = season_da.assign_coords(season_year=season_year)
        
        yearly = (season_da.groupby('season_year').map(apply_op)
                  .rename({'season_year': 'year'}))

    else:
        yearly = (season_da.groupby('time.year').map(apply_op))
        
    return yearly.mean('year').to_array()
	
def plot_map(da, period, var, season, ax):

	# fig, ax = plt.subplots(figsize=(9, 10))
	in_mm = '../shp/Jakarta_boundar.shp'
	in_ph = '../shp/Indo_Kab_Kot1.shp'
	# in_lake = 'shp/phl_lakes_062019/phl_lakes_062019.shp'

	ph_shp = gpd.read_file(in_ph).to_crs(epsg='4326')
	mm_shp = gpd.read_file(in_mm).to_crs(epsg='4326')

	t2_colors = ['#4A56F2', '#4BA0EA', '#6BDADB', '#8FF8C7', '#B2F9AC', 
				 '#D6DD8B', '#F2A865', '#EC633D', '#EA3323', '#b30000']
	cmapT2 = ListedColormap(t2_colors)
	cmapT2.set_under('#7514F5')
	cmapT2.set_over('#660000')

	tidx_colors = ['#fde0ddff', '#fcc5c0ff', '#fa9fb5ff', '#f768a1ff',
				   '#dd3497ff', '#ae017eff', '#7a0177ff', '#49006aff']
	cmapTidx = ListedColormap(tidx_colors)
	cmapTidx.set_under('#fff7f3ff')
	cmapTidx.set_over('#2d004dff')

	cmaps = {
		'TMean': cmapT2,
		'TXx': cmapT2,
		'TNn': cmapT2,
		'TX90p': cmapTidx, 
		'PHE': cmapTidx,
		'TN90p': cmapTidx,
	}

	#edit numbers depending on your 
	c1=[24, 24.5, 25, 25.5, 26, 26.5, 27, 27.5, 28, 28.5, 29]
	c2=[31, 31.5, 32, 32.5, 33, 33.5, 34, 34.5, 35, 35.6, 36]
	c3=[18, 18.5, 19, 19.5, 20, 20.5, 21, 21.5, 22, 22.5, 23]
	c4=[1, 6, 12, 18, 24, 30, 36, 42, 48]
	c5=[1, 12, 24, 36, 48, 60, 72, 80, 88]
	norms = {
		'TMean': mcolors.BoundaryNorm(c1, 10),
		'TXx': mcolors.BoundaryNorm(c2, 10),
		'TNn': mcolors.BoundaryNorm(c3, 10),
		'TX90p': mcolors.BoundaryNorm(c4, 8),
		'PHE': mcolors.BoundaryNorm(c4, 8),
		'TN90p': mcolors.BoundaryNorm(c5, 8),
	}
	# fig = px.imshow(
		# da[var].values,
		# origin="lower",
		# x=da.lon.values,
		# y=da.lat.values,
		# aspect="auto",
		# labels=dict(
			# x="Longitude",
			# y="Latitude"
		# ),
		# color_continuous_scale="Viridis"
	# )

	# st.plotly_chart(
		# fig,
		# use_container_width=True
	# )
	# im = ax.contourf(
	im = ax.pcolormesh(
		da.lon, da.lat, da[var],
		cmap=cmaps[var],
		norm=norms[var],
		shading='auto'
	)

	#edit based on your shapefile names
	ph_shp.boundary.plot(ax=ax, lw=.3, edgecolor='k')
	mm_shp.boundary.plot(ax=ax, lw=.7, edgecolor='b')
	mm_shp[mm_shp['PROVNO']=='31'].boundary.plot(ax=ax, lw=1., edgecolor='yellow')
	# lake_shp.boundary.plot(ax=ax, lw=1, edgecolor='k')

	ax.set_xlim(da.lon.min(), da.lon.max())
	ax.set_ylim(da.lat.min(), da.lat.max())
	ax.set_xticks([])
	ax.set_yticks([])

	# if i==4 or i==8 or i==15:
	cbar = fig.colorbar(im, ax=ax,
						orientation='vertical',
						shrink=0.5,
						extend='both',
						pad=0.02)
	# cbar.set_label(f"{season} {var_meta[var]['unit']}", fontsize=8)

	# outpath = out_dir / period / var
	# outpath.mkdir(parents=True, exist_ok=True)

	# fname = outpath / f'{city}_era5_{period}_{var}_{season}.png'

	# fig.savefig(fname, bbox_inches='tight', dpi=300, transparent=True)
	# plt.close()
	# south = float(da.lat.min())
	# north = float(da.lat.max())
	# west = float(da.lon.min())
	# east = float(da.lon.max())
	# center = [(south+north)/2,(west+east)/2]
	# m = leafmap.Map(
	# center=[-6, 106.6],
	# zoom=9)
	# m.add_raster(
	# im,
	# # layer_name=variable,
	# colormap="viridis",
	# )
	
	# m.add_layer_control()
	# m_streamlit = m.to_streamlit(800, 600)
	return im
#---------------------------------------------------------------------------------
@st.cache_data
def read_gdf(url, layer):
    gdf = gpd.read_file(url, layer=layer)
    return gdf

@st.cache_data
def read_csv(url):
    df = pd.read_csv(url)
    return df

@st.cache_data
def load_data(url):
    ds = xr.open_dataset(url)
    return ds

dir_path="../../../../scratch/den/hrldas/output/extract/JKT_nc_season"
dir1 = os.listdir(dir_path)
mods=['ENSEMBLE','EC-Earth3-Veg','NorESM2-MM','CanESM5','CMCC-ESM2']
mod = st.sidebar.selectbox('Select a model', mods)
# dir2 = os.listdir(dir_path + '/'+ mod)
# period = st.sidebar.selectbox('Select a period', dir2)
# fl = os.listdir(dir_path + '/'+ mod + '/'+ period)
vars=['TMean','TXx','TNn','TX90p','TN90p','PHE']
var = st.sidebar.selectbox('Choose a variable', vars)
seasons=['ANNUAL','DJF','MAM','JJA','SON']
season = st.sidebar.selectbox('Choose a season', seasons)
if mod=='EC-Earth3-Veg':
	mo='ec'
elif mod=='NorESM2-MM':
	mo='nor'
elif mod=='CanESM5':
	mo='can'
elif mod=='CMCC-ESM2':
	mo='cmcc'
else:
	mo='ens'

DATA_DIR = os.path.dirname(__file__)
# nc_url = os.path.join(DATA_DIR, dir_path, mod, period, var, season, f'{mo}_{period}_{var}_{season}.nc') 

try:
  print('ok')
  # ds = load_data(nc_url)
  # var = list(ds.data_vars)
  # da_sel = aggregate(ds[var], season, var);print(da_sel)
  # landmask = ds[var].isel(time=0).notnull()
  # da_sel = da_sel.where(landmask)
  # da_sel = da_sel.to_array();print(np.array(ds[var])[0])
  # Select a time slice or specific layer if 3D/4D data
  # da = ds[var].isel(
      # time=0
  # )  # Adjust dimensions as needed
  # Create Matplotlib figure
  # fig, ax = plt.subplots(figsize=(8, 6))
  # im=plot_map(ds, period, var, season,ax)
  # variable_name = st.sidebar.selectbox(
      # "Choose a variable", list(ds.data_vars)
  # )



  # # Use contourf with antialiased=False to avoid grid blemishes in Streamlit
  # cs = ax.contourf(
      # ds.lon,
      # ds.lat,
      # ds[var],
      # cmap="viridis",
      # antialiased=False,
  # )

  # fig.colorbar(cs, ax=ax, label=var)
  # ax.set_title(f"Contourf of {var}")
  # ax.set_xlabel("Longitude")
  # ax.set_ylabel("Latitude") 

  # Render in Streamlit
  # st.pyplot(fig)

except Exception as e:
  st.error(f"Error loading or plotting data: {e}")
# # Create the chart
# districts = districts_gdf.DISTRICT.values
# district = st.sidebar.selectbox('Select a District', districts)
# overlay = st.sidebar.checkbox('Overlay roads')
# district_lengths = lengths_df[lengths_df['DISTRICT'] == district]

# fig, ax = plt.subplots(1, 1)
# district_lengths.plot(kind='bar', ax=ax, color=['blue', 'red'],
    # ylabel='Kilometers', xlabel='Category')
# ax.get_xaxis().set_ticklabels([])
# ax.set_ylim(0, 2500)

# stats = st.sidebar.pyplot(fig)

# ## Create the map
# # fig=plt.figure()
# m = leafmap.Map(
	# center=[-6.2, 106.8],
	# zoom=8
# )
# # m.add_basemap('OpenStreetMap')
def nc2tif(nc_url, tif_file):
	ds = xr.open_dataset(nc_url)
	# ds = ds.assign_coords(time=0)
	# ds = ds.expand_dims(dim="time")
	ds = ds.drop_vars(
		[
			"quantile",
			"month",
			"time"
		],
		errors="ignore"
	)
	da = ds.squeeze()
	da = da.rio.set_spatial_dims(
		x_dim="lon",
		y_dim="lat"
	)

	da = da.rio.write_crs(
		"EPSG:4326"
		# "EPSG:3857"
	)
	# ds = ds.rename({"lat":"y","lon":"x"})
	# ds = ds.rio.write_crs("EPSG:4326")
	# tif_file="/home/danang-eko/.olah/.stream001/data/cf.tif"
	da.rio.to_raster(tif_file)
# # # print(ds)
# # # tmp_tif = tempfile.NamedTemporaryFile(
    # # # suffix=".tif",
    # # # delete=False
# # # )
# # # tmp_tif.close()
# # # tif_file = tmp_tif.name
# # ds.rio.to_raster(
    # # tif_file
# # )
# # with rasterio.open(tif_file) as src:

    # # print("CRS:", src.crs)
    # # print("Bounds:", src.bounds)
    # # print("Size:", src.width, src.height)
    # # print("Transform:", src.transform)
    # # print("Nodata:", src.nodata)
# # simpan ulang
# # ds.to_dataset(name=var).to_netcdf("cf.nc")
# # ds.to_netcdf("cf.nc")
# # nc_file = os.path.abspath("cf.tif");print(nc_file)
# # st.write("File:", nc_file)
# # st.write("Exists:", os.path.exists(nc_file))
# # st.write("Size:", os.path.getsize(nc_file))
# # ds.to_netcdf("rain_cf.nc");print(ds)
# # m.add_netcdf(nc_file,
    # # variable=var,
    # # layer_name=var,
    # # # palette="coolwarm",
# # )
# # ds = ds.astype("float32")
# da = ds[var]
# # da = da.astype("float32")
# # da = da.fillna(-9999)
# # da.rio.write_nodata(
    # # -9999,
    # # inplace=True
# # )
# # import rasterio
# # import numpy as np

def clean_nan_raster(input_path, output_path):
    with rasterio.open(input_path) as src:
        data = src.read(1)
        meta = src.meta.copy()
        
        # Replace actual NaN values with a standard numeric NoData value
        data[np.isnan(data)] = -9999
        
        # Update metadata properties to look for the new NoData flag
        meta.update({
            'nodata': -9999,
            'dtype': 'float32'
        })
        
        with rasterio.open(output_path, 'w', **meta) as dst:
            dst.write(data, 1)

# Run this once to generate a clean TIF, then feed 'clean_file.tif' into m.add_raster(nodata=-9999)
sce={'ENSEMBLE':'SSP','EC-Earth3-Veg':'SSP370','NorESM2-MM':'SSP370','CanESM5':'SSP370','CMCC-ESM2':'SSP245'}
nc_url1 = os.path.join(DATA_DIR, dir_path, mod, 'HIST', var, season, f'{mo}_HIST_{var}_{season}.nc') 
nc_url2 = os.path.join(DATA_DIR, dir_path, mod, sce[mod], var, season, f'{mo}_{sce[mod]}_{var}_{season}.nc') 
tif_file1="/home/danang-eko/.olah/.stream001/data/cf1.tif"
tif_file2="/home/danang-eko/.olah/.stream001/data/cf2.tif"
nc2tif(nc_url1, tif_file1);clean_nan_raster(tif_file1, tif_file1)
nc2tif(nc_url2, tif_file2);clean_nan_raster(tif_file2, tif_file2)

# da = da.squeeze()
# da = da.rio.set_spatial_dims(
    # x_dim="lon",
    # y_dim="lat"
# )

# da = da.rio.write_crs(
    # "EPSG:4326"
# )
# da.rio.to_raster(
    # tif_file,
    # driver="COG",
    # # compress="deflate"
# )
# with rasterio.open(tif_file) as src:
    # bounds = src.bounds
    # crs = src.crs
    # min_value = src.read(
        # 1,
        # masked=True
    # ).min()
    # max_value = src.read(
        # 1,
        # masked=True
    # ).max()
# print(min_value)	
# print(max_value)	
# # m.add_cog_layer(
    # # tif_file,
    # # layer_name=var,
    # # colormap_name="RdYlBu_r",
    # # opacity=0.8,
    # # rescale="0,0100"
    # # # rescale=f"{min_value},{max_value}"
    # # # colormap_name="turbo"
# # )
# # m.add_geotiff(
	# # tif_file,
	# # name=var,
	# # vmin=float(min_value),
	# # vmax=float(max_value),
	# # colormap_name="RdYlBu_r",
	# # opacity=0.9,
	# # nodata='transparent',
	# # # rescale="0,0100"
	# # # rescale=f"{min_value},{max_value}"
	# # # colormap_name="turbo"
# # )
# # colors = ["blue", "green", "red"]
# # m.add_colorbar(
    # # colors=colors,
    # # # cmap="RdYlBu",
    # # vmin=float(min_value),
    # # vmax=float(max_value),
    # # label="Climate Index"
# # )
# # m.add_raster(
	# # tif_file,
	# # layer_name=var,
	# # nodata=-9999,
	# # colormap="turbo"
# # )
# # m.add_netcdf("rain_cf.nc", variables=[var])
# # m.add_netcdf('wind_global.nc',
    # # variables=["v_wind"],
    # # palette="coolwarm",
    # # shift_lon=True,
    # # layer_name="v_wind",
    # # indexes=[1],
# # )
# # m.add_shp('../shp/Indo_Kab_Kot1.shp')
# # shpc=m.add_shp('../shp/Jakarta_boundar.shp');print(shpc)
# shp_file='../shp/Jakarta_boundar.shp'
# m.add_geojson(
    # shp_file,
    # layer_name="Kabupaten",
# )
# # folium.raster_layers.ImageOverlay(
    # # image=im,
    # # bounds=[
        # # [south,west],
        # # [north,east]
    # # ],
    # # opacity=0.7,
    # # interactive=True,
    # # cross_origin=False,
    # # zindex=1,
# # ).add_to(m)

# # folium.LayerControl().add_to(m)

# # st_folium(
    # # m,
    # # width=1200,
    # # height=700
# # )
# # # m.add_gdf(
    # # # gdf=districts_gdf,
    # # # zoom_to_layer=False,
    # # # layer_name='districts',
    # # # info_mode='on_click',
    # # # style={'color': '#7fcdbb', 'fillOpacity': 0.3, 'weight': 0.5},
    # # # )

# # # if overlay:
    # # # m.add_gdf(
        # # # gdf=roads_gdf,
        # # # zoom_to_layer=False,
        # # # layer_name='highways',
        # # # info_mode=None,
        # # # style={'color': '#225ea8', 'weight': 1.5},
    # # # )
    
# # # selected_gdf = districts_gdf[districts_gdf['DISTRICT'] == district]

# # # m.add_gdf(
    # # # gdf=selected_gdf,
    # # # layer_name='selected',
    # # # zoom_to_layer=True,
    # # # info_mode=None,
    # # # style={'color': 'yellow', 'fill': None, 'weight': 2}
 # # # )

# # m.add_layer_control()
# # m.add_opacity_control()
# m_streamlit = m.to_streamlit(height=700)
def mapvalue2color(value, cmap): 
    """
    Map a pixel value of image to a color in the rgba format. 
    As a special case, nans will be mapped totally transparent.
    
    Inputs
        -- value - pixel value of image, could be np.nan
        -- cmap - a linear colormap from branca.colormap.linear
    Output
        -- a color value in the rgba format (r, g, b, a)    
    """
    if np.isnan(value):
        return (1, 0, 0, 0)
    else:
        return colors.to_rgba(cmap(value), 0.7)  
		
# src = rasterio.open(tif_file1)
# array1 = src.read()
# bounds1 = src.bounds
# array1[array1<0.0]=np.nan
# x1,y1,x2,y2 = src.bounds
# # bbox = [(bounds.bottom, bounds.left), (bounds.top, bounds.right)]
# bbox1 = [[y1, x1], [y2, x2]]
# src = rasterio.open(tif_file2)
# array2 = src.read()
# bounds2 = src.bounds
# array2[array2<0.0]=np.nan
# x1,y1,x2,y2 = src.bounds
# # bbox = [(bounds.bottom, bounds.left), (bounds.top, bounds.right)]
# bbox2 = [[y1, x1], [y2, x2]]
# if var=='TMean' or var=='TXx' or var=='TNn':
	# vmin = 20 #np.floor(np.nanmin(array))
	# vmax = 38 #np.ceil(np.nanmax(array))
# elif var=='TX90p' or var=='PHE' or var=='TN90p':
	# vmin = 5 #np.floor(np.nanmin(array))
	# vmax = 90 #np.ceil(np.nanmax(array))
# colormap=cm.linear.RdBu_11.scale(vmin,vmax)
# colormap.colors.reverse()

# m = folium.Map(location=[-6.25, 106.8], zoom_start=10,
    # control_scale=True)
# img1 = folium.raster_layers.ImageOverlay(
	# name=var,
	# image=np.flipud(array1[0]), #np.moveaxis(array, 0, -1),
	# bounds=bbox1,
	# opacity=0.8,
	# interactive=True,
	# colormap= lambda value: mapvalue2color(value, colormap),
	# overlay=True,
	# cross_origin=False,
	# zindex=1,
	# control=False
# ).add_to(m)
# img2 = folium.raster_layers.ImageOverlay(
	# name=var,
	# image=np.flipud(array2[0]), #np.moveaxis(array, 0, -1),
	# bounds=bbox2,
	# opacity=0.8,
	# interactive=True,
	# colormap= lambda value: mapvalue2color(value, colormap),
	# overlay=True,
	# cross_origin=False,
	# zindex=2,
	# control=False
# ).add_to(m)

# # pup=folium.Popup("I am an image").add_to(img);print(pup)

# folium.plugins.SideBySideLayers(
    # layer_left=img1, layer_right=img2
# ).add_to(m)
# colormap.add_to(m)
# shp_file='../shp/Jakarta_boundar.shp'
# @st.cache_data
# def load_shp():
    # shp_df = gpd.read_file(shp_file)
    # return shp_df.to_json()

# layer_to_add = load_shp()
# # folium.GeoJson(
    # # layer_to_add,
    # # name="Kabupaten",style_function=lambda feature:      {"fillColor": "transparent", "color": "blue", "weight": 0.8, "fillOpacity": 0.4}
# # ).add_to(m)
# folium.LayerControl().add_to(m)

# # m = leafmap.Map(
	# # center=[-6.25, 106.8],
	# # zoom=10,
	# # control_scale=True
# # )
# # # m.add_raster(tif_file1, colormap="terrain", layer_name="My DEM Data")
# # m.split_map(left_layer=tif_file1, right_layer=tif_file2)

# ============================================================
# RASTER SPLIT MAP
# ============================================================

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

# ------------------------------------------------------------
# Read raster
# ------------------------------------------------------------

def read_raster(tif_file):
    with rasterio.open(tif_file) as src:

        data = src.read(1).astype("float32")

        # Raster bounds
        left = src.bounds.left
        bottom = src.bounds.bottom
        right = src.bounds.right
        top = src.bounds.top

        bounds = [
            [bottom, left],
            [top, right]
        ]

        print("Raster:", tif_file)
        print("CRS:", src.crs)
        print("Bounds:", src.bounds)
        print("Shape:", data.shape)
        print("Min:", np.nanmin(data))
        print("Max:", np.nanmax(data))

        # Convert nodata / invalid values to NaN
        if src.nodata is not None:
            data[data == src.nodata] = np.nan

        data[data < 0] = np.nan

    return data, bounds


array1, bbox1 = read_raster(tif_file1)
array2, bbox2 = read_raster(tif_file2)


# ------------------------------------------------------------
# Color scale
# ------------------------------------------------------------

# if var in ["TMean", "TXx", "TNn"]:

    # vmin = 20
    # vmax = 38

# elif var in ["TX90p", "PHE", "TN90p"]:

    # vmin = 5
    # vmax = 90

# else:

    # vmin = float(
        # np.nanmin(
            # np.concatenate([
                # array1[np.isfinite(array1)],
                # array2[np.isfinite(array2)]
            # ])
        # )
    # )

    # vmax = float(
        # np.nanmax(
            # np.concatenate([
                # array1[np.isfinite(array1)],
                # array2[np.isfinite(array2)]
            # ])
        # )
    # )

vmin = float(
	np.nanmin(
		np.concatenate([
			array1[np.isfinite(array1)],
			array2[np.isfinite(array2)]
		])
	)
)

vmax = float(
	np.nanmax(
		np.concatenate([
			array1[np.isfinite(array1)],
			array2[np.isfinite(array2)]
		])
	)
)


# ------------------------------------------------------------
# Matplotlib colormap
# ------------------------------------------------------------

cmap = plt.get_cmap("RdBu_r")
norm = Normalize(vmin=vmin, vmax=vmax, clip=True)


# ------------------------------------------------------------
# Convert raster values -> RGBA
# ------------------------------------------------------------

def raster_to_rgba(data):

    # Normalized values
    normalized = norm(
        np.nan_to_num(
            data,
            nan=vmin
        )
    )

    # RGBA, 0-1
    rgba = cmap(normalized)

    # Make NaN pixels transparent
    rgba[..., 3] = np.where(
        np.isfinite(data),
        0.85,
        0.0
    )

    # Convert to uint8
    rgba = (rgba * 255).astype(np.uint8)

    return rgba


rgba1 = raster_to_rgba(array1)
rgba2 = raster_to_rgba(array2)


# ------------------------------------------------------------
# Create Folium map
# ------------------------------------------------------------

center_lat = (
    bbox1[0][0] +
    bbox1[1][0]
) / 2

center_lon = (
    bbox1[0][1] +
    bbox1[1][1]
) / 2


m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=10,
    control_scale=True,
    tiles="OpenStreetMap"
)




# ------------------------------------------------------------
# Colorbar
# ------------------------------------------------------------
 
title = {
	'TMean': 'Mean of daily mean temperature [°C]',
	'TXx': 'Max of daily max temperature [°C]',
	'TNn': 'Min of daily min temperature [°C]',
	'TX90p': 'Percentage of days with TMax\nabove the historical 90th percentile', 
	'PHE': 'Number of days belonging to persistent heat extremes\n≥5 consecutive days with TMax above the historical 90th percentile',
	'TN90p': 'Percentage of days with TMin\nabove the historical 90th percentile',
}
colormap = cm.LinearColormap(
    colors=[
        "#053061",
        "#2166ac",
        "#67a9cf",
        "#d1e5f0",
        "#f7f7f7",
        "#f4a582",
        "#d6604d",
        "#b2182b",
        "#67001f"
    ],
    vmin=vmin,
    vmax=vmax,
    caption=title[var]
)



# ------------------------------------------------------------
# Jakarta boundary
# ------------------------------------------------------------

shp_file = "../shp/Jakarta_boundar.shp"


@st.cache_data
def load_shp():
    shp_df = gpd.read_file(shp_file)

    # Make sure boundary is WGS84
    if shp_df.crs is not None:
        shp_df = shp_df.to_crs("EPSG:4326")

    return shp_df.to_json()


layer_to_add = load_shp()

shp_jkt=folium.GeoJson(
    layer_to_add,
    name="Jakarta Boundary",
    style_function=lambda feature: {
        "fillColor": "transparent",
        "fillOpacity": 0,
        "color": "yellow",
        "weight": 2
    }
)
# ------------------------------------------------------------
# LEFT / HISTORICAL RASTER
# ------------------------------------------------------------

img1 = folium.raster_layers.ImageOverlay(
    image=np.flipud(rgba1),
    bounds=bbox1,
    opacity=0.9,
    # interactive=True,
    # cross_origin=False,
    zindex=1,
    name="Historical",
    # overlay=True,
    control=False
)

img1.add_to(m)
colormap.add_to(m)
shp_jkt.add_to(m)


# ------------------------------------------------------------
# RIGHT / FUTURE RASTER
# ------------------------------------------------------------

img2 = folium.raster_layers.ImageOverlay( 
    image=np.flipud(rgba2),
    bounds=bbox2,
    opacity=0.9,
    # interactive=True,
    # cross_origin=False,
    zindex=2,
    name="Future",
    # overlay=True,
    control=False
)

img2.add_to(m)
colormap.add_to(m)
shp_jkt.add_to(m)

# m.fit_bounds(bbox1)
# ------------------------------------------------------------
# SIDE-BY-SIDE SLIDER
# ------------------------------------------------------------

folium.plugins.SideBySideLayers(
    layer_left=img1,
    layer_right=img2
).add_to(m)


# ------------------------------------------------------------
# Layer control
# ------------------------------------------------------------

folium.LayerControl().add_to(m)

st.title(title[var])

# ------------------------------------------------------------
# Display Streamlit map
# ------------------------------------------------------------

# st_folium(
folium_static(
    m,
    width=735,
    height=735,
    # returned_objects=[]
)

# # call to render Folium map in Streamlit
# st_folium(m, width=700, height=700)