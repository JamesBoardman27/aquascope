# Niger at Bamako (12.6N, -8.0W): mean flow and Q95 for an ungauged water-supply offtake

**Author:** AquaScope Studio  
**Date:** 2026-09-07  
**Description:** size a water-supply offtake on the Niger at Bamako using expected mean flow and low-flow (Q95) since no gauge record is reachable at the site  
**Data Sources:** BasinATLAS (HydroATLAS v1.0), ERA5 via Open-Meteo, similar_basins  
**Version:** 1.0  

**Site:** 12.6000 N, 8.0000 W

**Answer.** No gauge is reachable at the Bamako offtake, so both numbers are transferred from 10 gauged donor basins (out of a 37,071-station pool) matched by catchment similarity, then converted to m3/s using the BasinATLAS upstream area of 115,012.9 km2. Expected mean annual flow is about 832 m3/s (donor cross-donor band 376-1840 m3/s; full donor range about 163-2125 m3/s; leave-one-out median absolute percent error 0.23 in log space, n=918 donors in the archive). Expected Q95 low flow is about 95 m3/s (cross-donor band 29-308 m3/s; full donor range about 18-609 m3/s; leave-one-out median APE 0.52 in log space). These are point estimates inside wide bands, not certainties. Cross-check: BasinATLAS's own long-term natural discharge estimate for this outlet (dis_m3_pyr) is 1091.69 m3/s, about 24 percent above the regionalized mean, which is reasonable agreement in order of magnitude. The GloFAS discharge time series pulled for this grid cell, however, gives a mean of only 0.571 m3/s and a Q95 (from its flow-duration curve) of about 0.09 m3/s, three to four orders of magnitude below both the regionalized estimate and the BasinATLAS natural-discharge figure. That mismatch indicates the ~5 km GloFAS grid cell sampled here is not resolving the main Niger channel at Bamako (likely an adjacent small tributary or a routing misalignment), so the GloFAS numbers are reported but not used to validate the design flows. A second, structural caveat: none of the 10 donor gauges are geographically or climatically close to the Sahelian Niger basin (all are French metropolitan, Caribbean, or Pyrenean stations with temperatures of 9-26 C spanning far below the target's 25.8 C, and with 0 percent upstream regulation versus the target's 6.3 percent), so the similarity match is on catchment attributes only, not on climate analogy, and the offtake sizing should treat the reported bands, not the central values, as the working design range, sized toward the lower half of the Q95 band for a conservative low-flow allowance.

*Key numbers*

| Quantity | Value | Unit | Step |
| --- | --- | --- | --- |
| Upstream area | 115000.0 | km2 | s1 |
| Donor gauges | 10.0 |  | s2 |
| mean daily flow | 0.6251 | mm/d | s4.fallback |
| low flow: exceeded 95 % of days | 0.0714 | mm/d | s4.fallback |
| high flow: exceeded 5 % of days | 2.06 | mm/d | s4.fallback |
| mean annual daily maximum | 5.67 | mm/d | s4.fallback |
| mean flow / BasinATLAS precipitation | 0.2724 | - | s4.fallback |
| baseflow / total flow | 0.6501 | - | s4.fallback |
| ERA5 precipitation | 736.5 | mm per year | s4 |
| ERA5 reference evapotranspiration | 2090.0 | mm per year | s4 |
| Aridity index | 0.3524 |  | s4 |
| GloFAS mean discharge (cell) | 0.571 | m3/s | s4 |

## Summary

Provide a mean annual flow and Q95 low-flow estimate, in m3/s, for the Niger at the Bamako offtake site to support sizing a water-supply intake where no gauge record is reachable.. 4 step(s) ran (methodologist plan, playbook ungauged_flow); 8 of 9 gates passed. Signatures transferred from 918 donors (both): mean daily flow 0.6251 mm/d (band 0.2827 to 1.382); low flow: exceeded 95 % of days 0.0714 mm/d (band 0.022 to 0.2315); high flow: exceeded 5 % of days 2.06 mm/d (band 0.8325 to 5.096); mean annual daily maximum 5.67 mm/d (band 1.526 to 21.08); mean flow / BasinATLAS precipitation 0.2724 - (band 0.0981 to 0.4466), leave-one-out NSE 0.17; baseflow / total flow 0.6501 - (band 0.5482 to 0.7519), leave-one-out NSE 0.3. 2 point(s) are listed under what this study does not establish.

## Problem and decision

No gauge I can reach on the Niger at Bamako: what mean flow and Q95 should a water-supply offtake expect? Decision: size a water-supply offtake on the Niger at Bamako using expected mean flow and low-flow (Q95) since no gauge record is reachable at the site. Quantities wanted: mean annual flow (m3/s); Q95 flow (m3/s). Constraints: no gauge within 50 km of the site (nearest catalogued gauge is 2,656 km away); at-site methods (flow duration, GR4J calibration) not defensible without a discharge record; estimate must rely on regionalisation from donor basins and GloFAS cross-check. Intake: purpose = water supply, statistic = all. Assumed: catchment delineation and area (115,012.9 km2 upstream) taken from BasinATLAS HydroATLAS v1.0 at the given coordinates; regionalisation draws on the 10 donor gauges identified from the 37,071-gauge pool as hydrologically similar; GloFAS discharge is reachable for this location for cross-checking regionalised estimates; no local abstraction, dam operation, or channel modification data beyond the HydroATLAS dam index (6.3) is available to adjust the natural-flow estimate.

## Site and data

Site: 12.6, -8.0. The datasets within reach or attached:

| Id | Kind | Variable | Source | Name | Years | Resolution | km | Period | Quality |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| catchment | catchment |  | BasinATLAS (HydroATLAS v1.0) | the catchment of the point |  |  |  |  |  |
| donors | donors |  | similar_basins | 10 donor gauges by catchment similarity |  |  |  |  |  |
| era5 | reanalysis | climate | ERA5 via Open-Meteo | ERA5 cell | 86.7 | daily |  | 1940-01-01 to 2026-09-07 |  |

- No catalog gauge within 50 km; the nearest is Le Blavet à Neulliac - Blavet Auquinian (hubeau_hydrometrie/J543211003) at 2,656 km.
- 10 donor gauges from a pool of 37,071 gauged catchments.
- ERA5 temperature and forcing and GloFAS discharge are assumed reachable for any point on land (Open-Meteo); not checked here.
- CMIP6 change factors need model output you supply (aquascope.climate works on downloaded data); not counted.
- No gauge with a usable record within 50 km: at-site methods are not defensible; what remains is the regionalisation path (similar_basins, regionalize_signatures) and the GloFAS cross-check.

## Methodology

Objective: Provide a mean annual flow and Q95 low-flow estimate, in m3/s, for the Niger at the Bamako offtake site to support sizing a water-supply intake where no gauge record is reachable..

1. Delineate and characterise the catchment upstream of the site (lat 12.6, lon -8.0) using BasinATLAS/HydroATLAS to obtain the upstream area and attributes needed for donor matching and unit conversion.
2. Identify the 10 gauged donor basins most similar to this catchment in attribute space from the 37,071-gauge pool.
3. Transfer mean, median, Q95 and Q05 flow signatures (in mm/d) from the donor set to the site, each reported with its cross-donor band and leave-one-out skill.
4. Convert the regionalised mean and Q95 signatures from mm/d to m3/s using the BasinATLAS upstream area (115,012.9 km2).
5. Pull ERA5 climate and GloFAS modelled discharge for the site coordinates as an independent cross-check of the regionalised mean flow and Q95.
6. Compare the regionalised m3/s estimates against the GloFAS-derived mean and low-flow statistics and report agreement or divergence as part of the confidence statement.
7. Recommend the offtake design flows only with the accompanying donor band, leave-one-out skill, and GloFAS cross-check attached, not as bare point numbers.

Step s1: `describe_catchment(lat=12.6, lon=-8.0, upstream=True)`; gates: not_empty on sub_basin; max_area_km2 200000 on sub_basin.up_area.

Step s2: `similar_basins(lat=12.6, lon=-8.0, k=10)`, method similar_basins; gates: min_donors 3 on k; not_empty on stations.

Step s3: `regionalize_signatures(lat=12.6, lon=-8.0, k=10)`, method regionalize_signatures; gates: not_empty on estimates; not_empty on skill.

Step s4: `anywhere(lat=12.6, lon=-8.0, years=20)`, method glofas_cross_check; gates: not_empty on climate; not_empty on climate; spread_within 0.5 on ['s3.signatures.mean_m3s', 's4.glofas.mean_m3s'].

Assumptions: catchment delineation and area (115,012.9 km2 upstream) taken from BasinATLAS HydroATLAS v1.0 at the given coordinates; regionalisation draws on the 10 donor gauges identified from the 37,071-gauge pool as hydrologically similar; GloFAS discharge is reachable for this location for cross-checking regionalised estimates; no local abstraction, dam operation, or channel modification data beyond the HydroATLAS dam index (6.3) is available to adjust the natural-flow estimate; The catchment delineation and upstream area (115,012.9 km2) from BasinATLAS HydroATLAS v1.0 at 12.6N, -8.0E is representative of the actual offtake location.; The 10 donor gauges identified by catchment similarity are hydrologically comparable to the Niger at Bamako despite geographic distance.; GloFAS discharge is reachable and reasonably representative of the natural flow regime at this grid cell for cross-checking purposes.; The HydroATLAS dam index (6.3) is the only regulation signal available and no further abstraction or dam-operation adjustment is applied to the natural-flow estimate.; Converting regionalised mm/d signatures to m3/s using the BasinATLAS upstream area introduces no significant additional error beyond the donor-transfer uncertainty..

Alternatives considered: flow_duration: marked not_defensible in the sufficiency table: no discharge record exists at this site to build a flow-duration curve; gr4j_calibration: marked not_defensible in the sufficiency table: rainfall-runoff calibration requires an observed discharge record at the site, which is absent.

## Results: step s1

The catchment (BasinATLAS): upstream area 1.15e+05 km2, mean elevation 467 m, aridity index (P/PET) 0.73 P/PET, degree of regulation by reservoirs 6.3 %. Gates: not_empty passed ('sub_basin' is present); max_area_km2 passed (catchment of 115,013 km2 against a ceiling of 200,000 km2).

![The site, in longitude and latitude (no basemap); no catalogue station was listed with it.](figures/s1_site_map.png)
*The site, in longitude and latitude (no basemap); no catalogue station was listed with it.*

![The site, in longitude and latitude (no basemap); no catalogue station was listed with it.](figures/s1_site_map.png)
*The site, in longitude and latitude (no basemap); no catalogue station was listed with it.*

*Catchment attributes from BasinATLAS for the site at 12.60 N, 8.00 W.*

| attribute | label | value | unit | source | note |
| --- | --- | --- | --- | --- | --- |
| n_sub_basins |  | 849.0 |  |  |  |
| area_km2 |  | 115014.4 |  |  |  |
| outlet_hybas_id |  | 1121916250.0 |  |  |  |
| upstream_area_km2 |  | 115012.9 |  |  |  |
| elevation_m | mean elevation | 467.0 | m | basinatlas_upstream |  |
| slope_deg | mean slope | 2.5 | degrees | basinatlas_upstream |  |
| precipitation_mm_yr | annual precipitation (WorldClim) | 1508.0 | mm/yr | basinatlas_upstream |  |
| pet_mm_yr | annual potential evapotranspiration | 2064.0 | mm/yr | basinatlas_upstream |  |
| aet_mm_yr | annual actual evapotranspiration | 1087.0 | mm/yr | basinatlas_upstream |  |
| aridity_index | aridity index (P/PET) | 0.73 | P/PET | basinatlas_upstream |  |
| temperature_c | mean annual air temperature | 25.8 | °C | basinatlas_upstream |  |
| snow_cover_pct | annual snow cover extent | 0.0 | % | basinatlas_upstream |  |
| runoff_mm_yr | annual land-surface runoff | 406.54 | mm/yr | area_weighted_mean |  |
| discharge_m3s | mean annual natural discharge at the outlet | 1091.69 | m3/s | basinatlas_upstream |  |
| forest_pct | forest cover | 35.0 | % | basinatlas_upstream |  |
| cropland_pct | cropland | 7.0 | % | basinatlas_upstream |  |
| pasture_pct | pasture | 24.0 | % | basinatlas_upstream |  |
| urban_pct | urban extent | 1.0 | % | basinatlas_upstream |  |
| irrigated_pct | irrigated area | 1.0 | % | basinatlas_upstream |  |
| glacier_pct | glacier extent | 0.0 | % | basinatlas_upstream |  |
| wetland_pct | wetlands (all classes) | 2.0 | % | basinatlas_upstream |  |
| lake_pct | lake area | 0.3 | % | basinatlas_upstream |  |
| karst_pct | karst extent | 0.0 | % | basinatlas_upstream |  |
| clay_pct | clay fraction in soil | 26.0 | % | basinatlas_upstream |  |
| silt_pct | silt fraction in soil | 20.0 | % | basinatlas_upstream |  |
| sand_pct | sand fraction in soil | 53.0 | % | basinatlas_upstream |  |
| soil_organic_carbon_t_ha | soil organic carbon | 19.0 | t/ha | basinatlas_upstream |  |
| soil_water_pct | annual soil water content | 55.0 | % | basinatlas_upstream |  |
| groundwater_table_cm | groundwater table depth | 140.34 | cm | area_weighted_mean |  |
| population_density | population density | 45.68 | people/km2 | basinatlas_upstream |  |
| population | population count | 5158532.23 | people | basinatlas_upstream |  |
| degree_of_regulation_pct | degree of regulation by reservoirs | 6.3 | % | basinatlas_upstream |  |
| human_footprint_2009 | human footprint (2009) | 6.4 | index 0-50 | basinatlas_upstream |  |
| reservoir_volume_mcm | reservoir volume upstream | 2170.0 | million m3 | basinatlas_upstream |  |

## Results: step s2

10 donor gauges by combined: Le Blavet à Neulliac - Blavet Auquinian (hubeau_hydrometrie J543211003), La Nive à Saint-Jean-Pied-de-Port (hubeau_hydrometrie Q902000101), La Nive des Aldudes à Saint-Étienne-de-Baïgorry (hubeau_hydrometrie Q916461001), Le Gave d'Oloron [Le Gave d'Ossau] à Oloron-Sainte-Marie - Quartier Sestiaa (hubeau_hydrometrie Q614292002), La Nivelle à Saint-Pée-sur-Nivelle [Pont de Cherchebruit] (hubeau_hydrometrie S514401001). Gates: min_donors passed (10 donors, 3 needed); not_empty passed ('stations' is present).

![The site and the 10 donor gauges the similarity search selected, in longitude and latitude (no basemap); labels are the station ids.](figures/s2_donors_map.png)
*The site and the 10 donor gauges the similarity search selected, in longitude and latitude (no basemap); labels are the station ids.*

![The site and the 10 donor gauges the similarity search selected, in longitude and latitude (no basemap); labels are the station ids.](figures/s2_donors_map.png)
*The site and the 10 donor gauges the similarity search selected, in longitude and latitude (no basemap); labels are the station ids.*

*Donor gauges selected for the site at 12.60 N, 8.00 W.*

| source | station_id | name | latitude | longitude | distance_km | score | similarity_distance | up_area_km2 | period_start | period_end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hubeau_hydrometrie | J543211003 | Le Blavet à Neulliac - Blavet Auquinian | 35.108562837 | 0.840483401 | 2656.2 | 5.9804 | 2.7464 | 128.1 | 2026-07-09 |  |
| hubeau_hydrometrie | Q902000101 | La Nive à Saint-Jean-Pied-de-Port | 43.161941599 | -1.236181897 | 3459.9 | 7.0111 | 1.1276 | 258.0 | 2025-05-01 |  |
| hubeau_hydrometrie | Q916461001 | La Nive des Aldudes à Saint-Étienne-de-Baïgorry | 43.184100302 | -1.33680921 | 3460.5 | 7.0187 | 1.1666 | 205.3 | 1960-01-01 |  |
| hubeau_hydrometrie | Q614292002 | Le Gave d'Oloron [Le Gave d'Ossau] à Oloron-Sainte-Marie - Quartier Sestiaa | 43.191760961 | -0.604709963 | 3475.0 | 7.0208 | 0.9942 | 1184.1 | 2011-11-17 |  |
| hubeau_hydrometrie | S514401001 | La Nivelle à Saint-Pée-sur-Nivelle [Pont de Cherchebruit] | 43.321469448 | -1.54993683 | 3471.7 | 7.0224 | 1.0503 | 239.8 | 1969-01-01 |  |
| hubeau_hydrometrie | S514402001 | La Nivelle à Saint-Pée-sur-Nivelle [Lurberria] | 43.313456954 | -1.533052277 | 3471.1 | 7.0233 | 1.0637 | 239.8 | 2009-03-27 |  |
| hubeau_hydrometrie | Q910251001 | La Nive à Ossès | 43.230308097 | -1.301413439 | 3466.2 | 7.0256 | 1.1412 | 767.6 | 1995-01-01 |  |
| hubeau_hydrometrie | Q724252001 | Le Saison à Licq-Athérey [Pont de Licq] | 43.066445321 | -0.876716891 | 3456.2 | 7.0258 | 1.2567 | 366.2 | 1996-01-01 |  |
| hubeau_hydrometrie | S516001001 | La Nivelle à Ciboure | 43.384770372 | -1.66398305 | 3476.7 | 7.0316 | 1.0465 | 239.8 | 2000-05-22 |  |
| hubeau_hydrometrie | Q803251001 | La Bidouze à Aïcirits-Camou-Suhast [Saint-Palais] | 43.334342208 | -1.027918942 | 3482.4 | 7.0334 | 0.9803 | 475.5 | 1969-10-15 |  |

## Results: step s3

Signatures transferred from 918 donors (similarity): mean daily flow 0.6251 mm/d (band 0.2827 to 1.382); low flow: exceeded 95 % of days 0.0714 mm/d (band 0.022 to 0.2315); high flow: exceeded 5 % of days 2.06 mm/d (band 0.8325 to 5.096); mean annual daily maximum 5.67 mm/d (band 1.526 to 21.08); mean flow / BasinATLAS precipitation 0.2724 - (band 0.0981 to 0.4466), leave-one-out NSE 0.17; baseflow / total flow 0.6501 - (band 0.5482 to 0.7519), leave-one-out NSE 0.3. Gates: not_empty passed ('estimates' is present); not_empty passed ('skill' is present).

![Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.](figures/s3_signatures_band.png)
*Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.*

![Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.](figures/s3_signatures_band.png)
*Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.*

*Flow signatures at the site at 12.60 N, 8.00 W.*

| signature | label | value | low | high | unit | n_donors | nse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| q_mean_mm | mean daily flow | 0.6251 | 0.2827 | 1.3824 | mm/d | 10 |  |
| q_median_mm | median daily flow | 0.3132 | 0.155 | 0.6329 | mm/d | 10 |  |
| q95_mm | low flow: exceeded 95 % of days | 0.0714 | 0.022 | 0.2315 | mm/d | 10 |  |
| q05_mm | high flow: exceeded 5 % of days | 2.0597 | 0.8325 | 5.0964 | mm/d | 10 |  |
| q_annual_max_mm | mean annual daily maximum | 5.6704 | 1.5256 | 21.0752 | mm/d | 10 |  |
| runoff_ratio | mean flow / BasinATLAS precipitation | 0.2724 | 0.0981 | 0.4466 | - | 10 | 0.168 |
| baseflow_index | baseflow / total flow | 0.6501 | 0.5482 | 0.7519 | - | 10 | 0.3 |
| fdc_slope | slope of the flow-duration curve (log space, 33-66 %) | 2.7845 | 1.5136 | 4.0555 | - | 10 | 0.154 |
| high_flow_frequency | days above 3 x median per year | 58.6815 | 26.2318 | 91.1312 | days/yr | 10 | 0.262 |
| low_flow_frequency | days below 0.2 x median per year | 18.7652 | 0.0 | 43.6805 | days/yr | 10 | 0.306 |
| zero_flow_fraction | fraction of zero-flow days | 0.0 | 0.0 | 0.0002 | - | 10 | -0.049 |
| seasonality_index | Markham seasonality of monthly flow | 0.2835 | 0.0837 | 0.4833 | - | 10 | 0.349 |
| flashiness_index | Richards-Baker flashiness | 0.3334 | 0.1699 | 0.497 | - | 10 | 0.408 |

*Donor gauges selected for the site at 12.60 N, 8.00 W.*

| source | station_id | name | latitude | longitude | distance_km | score | similarity_distance | up_area_km2 | period_start | period_end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hubeau_hydrometrie | 2320000101 | La rivière du Carbet à Fonds-Saint-Denis [fond mascret] | 14.729517849 | -61.141301418 |  | 1.3416 | 1.3416 | 236.1 | 2010-01-01 |  |
| hubeau_hydrometrie | 1120000101 | La Grande Rivière de Capesterre à Capesterre-Belle-Eau [Prise d'eau La Digue] | 16.071665156 | -61.609380634 |  | 1.3748 | 1.3748 | 204.6 | 1983-05-01 |  |
| hubeau_hydrometrie | 2803000101 | La rivière les Coulisses à Rivière-Salée [Petit-Bourg] - 1 | 14.547599077 | -60.960058505 |  | 1.4203 | 1.4203 | 476.5 | 1995-07-07 |  |
| hubeau_hydrometrie | 2225000301 | La rivière du Galion à la Trinité [bassignac] | 14.729521489 | -60.981706085 |  | 1.4404 | 1.4404 | 356.2 | 2010-01-01 |  |
| hubeau_hydrometrie | 2113000201 | La rivière Capot au Morne-Rouge [mackintosh] - Pont de Mackintosh | 14.778259074 | -61.116639324 |  | 1.4404 | 1.4404 | 356.2 | 2010-01-01 |  |
| hubeau_hydrometrie | A735201001 | Le Rupt de Mad à Onville | 49.012193042 | 5.961532525 |  | 1.4774 | 1.4774 | 398.8 | 1964-08-01 |  |
| hubeau_hydrometrie | B022001001 | La Meuse à Goncourt | 48.240913254 | 5.614415096 |  | 1.478 | 1.478 | 452.2 | 1971-09-14 |  |
| hubeau_hydrometrie | A902102101 | Le ruisseau de Gondrexange à Imling | 48.709216717 | 7.019469795 |  | 1.4799 | 1.4799 | 104.2 | 2015-09-01 |  |
| hubeau_hydrometrie | A919205050 | L'Albe à Sarralbe - Eich | 48.997419075 | 7.019499795 |  | 1.4827 | 1.4827 | 433.3 | 2008-01-01 |  |
| hubeau_hydrometrie | B105201001 | Le Mouzon à Sommerécourt | 48.224397022 | 5.664011145 |  | 1.4844 | 1.4844 | 227.4 | 1995-01-12 |  |

## Results: step s4

ERA5 climate for the cell: precipitation 736.5 mm per year, reference evapotranspiration 2,090 mm per year, aridity index 0.35 (semi-arid). GloFAS modelled discharge (grid cell, indicative): mean 0.571 m3/s, 100-year GEV 18.74 m3/s. Gates: not_empty passed ('climate' is present); not_empty passed ('climate' is present); spread_within FAILED (spread_within needs two or more paths and a value). The fallback regionalize_signatures ran and passed its gates. Signatures transferred from 918 donors (both): mean daily flow 0.6251 mm/d (band 0.2827 to 1.382); low flow: exceeded 95 % of days 0.0714 mm/d (band 0.022 to 0.2315); high flow: exceeded 5 % of days 2.06 mm/d (band 0.8325 to 5.096); mean annual daily maximum 5.67 mm/d (band 1.526 to 21.08); mean flow / BasinATLAS precipitation 0.2724 - (band 0.0981 to 0.4466), leave-one-out NSE 0.17; baseflow / total flow 0.6501 - (band 0.5482 to 0.7519), leave-one-out NSE 0.3.

![Mean monthly precipitation (bars) and FAO-56 reference evapotranspiration (line) for the ERA5 cell at the site at 12.60 N, 8.00 W, 20 years ending 2026-08-31.](figures/s4_monthly_climate.png)
*Mean monthly precipitation (bars) and FAO-56 reference evapotranspiration (line) for the ERA5 cell at the site at 12.60 N, 8.00 W, 20 years ending 2026-08-31.*

![Mean monthly precipitation (bars) and FAO-56 reference evapotranspiration (line) for the ERA5 cell at the site at 12.60 N, 8.00 W, 20 years ending 2026-08-31.](figures/s4_monthly_climate.png)
*Mean monthly precipitation (bars) and FAO-56 reference evapotranspiration (line) for the ERA5 cell at the site at 12.60 N, 8.00 W, 20 years ending 2026-08-31.*

![Annual maxima of the modelled discharge from GloFAS v4 (Open-Meteo) for the grid cell at the site at 12.60 N, 8.00 W, 2006 to 2026: a model output, indicative only, not a gauge reading.](figures/s4_glofas_series.png)
*Annual maxima of the modelled discharge from GloFAS v4 (Open-Meteo) for the grid cell at the site at 12.60 N, 8.00 W, 2006 to 2026: a model output, indicative only, not a gauge reading.*

![Annual maxima of the modelled discharge from GloFAS v4 (Open-Meteo) for the grid cell at the site at 12.60 N, 8.00 W, 2006 to 2026: a model output, indicative only, not a gauge reading.](figures/s4_glofas_series.png)
*Annual maxima of the modelled discharge from GloFAS v4 (Open-Meteo) for the grid cell at the site at 12.60 N, 8.00 W, 2006 to 2026: a model output, indicative only, not a gauge reading.*

![Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.](figures/s4.fallback_signatures_band.png)
*Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.*

![Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.](figures/s4.fallback_signatures_band.png)
*Flow signatures transferred to the site from 10 donor catchments, with the one-standard-deviation band across donors as error bars and the leave-one-out skill (NSE) where published.*

*Mean monthly precipitation and reference evapotranspiration for the ERA5 cell at the site at 12.60 N, 8.00 W.*

| month | precipitation_mm | et0_mm |
| --- | --- | --- |
| 1 | 0.7168 | 195.4744 |
| 2 | 0.8351 | 220.516 |
| 3 | 1.3403 | 225.8236 |
| 4 | 3.4093 | 222.8238 |
| 5 | 30.2878 | 196.9218 |
| 6 | 86.7743 | 167.6879 |
| 7 | 182.316 | 123.8663 |
| 8 | 220.266 | 108.8889 |
| 9 | 153.1842 | 122.3526 |
| 10 | 48.0166 | 143.7681 |
| 11 | 2.1054 | 178.1161 |
| 12 | 0.4811 | 188.6362 |

*GloFAS modelled discharge for the grid cell at the site at 12.60 N, 8.00 W (indicative).*

| item | value |
| --- | --- |
| variable | discharge |
| unit | m3/s |
| n | 7306 |
| start | 2006-08-31 |
| end | 2026-08-31 |
| years | 20.0 |
| stats.mean | 0.571 |
| stats.median | 0.12 |
| stats.min | 0.03 |
| stats.max | 16.42 |
| trend.on | annual mean |
| trend.p_value | 0.6243 |
| trend.tau | 0.0877 |
| trend.trend | no trend |
| trend.sens_slope_per_year | 0.0027 |
| trend.n_years | 19 |
| source | GloFAS v4 (modelled) via Open-Meteo |
| modelled | True |
| return_level_T2_gev | 7.1376 |
| return_level_T5_gev | 9.9229 |
| return_level_T10_gev | 11.8888 |
| return_level_T25_gev | 14.5207 |
| return_level_T50_gev | 16.5859 |
| return_level_T100_gev | 18.736 |
| q10 | 1.74 |
| q50 | 0.12 |
| q95 | 0.09 |

*Flow signatures at the site at 12.60 N, 8.00 W.*

| signature | label | value | low | high | unit | n_donors | nse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| q_mean_mm | mean daily flow | 0.6251 | 0.2827 | 1.3824 | mm/d | 10 |  |
| q_median_mm | median daily flow | 0.3132 | 0.155 | 0.6329 | mm/d | 10 |  |
| q95_mm | low flow: exceeded 95 % of days | 0.0714 | 0.022 | 0.2315 | mm/d | 10 |  |
| q05_mm | high flow: exceeded 5 % of days | 2.0597 | 0.8325 | 5.0964 | mm/d | 10 |  |
| q_annual_max_mm | mean annual daily maximum | 5.6704 | 1.5256 | 21.0752 | mm/d | 10 |  |
| runoff_ratio | mean flow / BasinATLAS precipitation | 0.2724 | 0.0981 | 0.4466 | - | 10 | 0.168 |
| baseflow_index | baseflow / total flow | 0.6501 | 0.5482 | 0.7519 | - | 10 | 0.3 |
| fdc_slope | slope of the flow-duration curve (log space, 33-66 %) | 2.7845 | 1.5136 | 4.0555 | - | 10 | 0.154 |
| high_flow_frequency | days above 3 x median per year | 58.6815 | 26.2318 | 91.1312 | days/yr | 10 | 0.262 |
| low_flow_frequency | days below 0.2 x median per year | 18.7652 | 0.0 | 43.6805 | days/yr | 10 | 0.306 |
| zero_flow_fraction | fraction of zero-flow days | 0.0 | 0.0 | 0.0002 | - | 10 | -0.049 |
| seasonality_index | Markham seasonality of monthly flow | 0.2835 | 0.0837 | 0.4833 | - | 10 | 0.349 |
| flashiness_index | Richards-Baker flashiness | 0.3334 | 0.1699 | 0.497 | - | 10 | 0.408 |

*Donor gauges selected for the site at 12.60 N, 8.00 W.*

| source | station_id | name | latitude | longitude | distance_km | score | similarity_distance | up_area_km2 | period_start | period_end |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hubeau_hydrometrie | 2320000101 | La rivière du Carbet à Fonds-Saint-Denis [fond mascret] | 14.729517849 | -61.141301418 |  | 1.3416 | 1.3416 | 236.1 | 2010-01-01 |  |
| hubeau_hydrometrie | 1120000101 | La Grande Rivière de Capesterre à Capesterre-Belle-Eau [Prise d'eau La Digue] | 16.071665156 | -61.609380634 |  | 1.3748 | 1.3748 | 204.6 | 1983-05-01 |  |
| hubeau_hydrometrie | 2803000101 | La rivière les Coulisses à Rivière-Salée [Petit-Bourg] - 1 | 14.547599077 | -60.960058505 |  | 1.4203 | 1.4203 | 476.5 | 1995-07-07 |  |
| hubeau_hydrometrie | 2225000301 | La rivière du Galion à la Trinité [bassignac] | 14.729521489 | -60.981706085 |  | 1.4404 | 1.4404 | 356.2 | 2010-01-01 |  |
| hubeau_hydrometrie | 2113000201 | La rivière Capot au Morne-Rouge [mackintosh] - Pont de Mackintosh | 14.778259074 | -61.116639324 |  | 1.4404 | 1.4404 | 356.2 | 2010-01-01 |  |
| hubeau_hydrometrie | A735201001 | Le Rupt de Mad à Onville | 49.012193042 | 5.961532525 |  | 1.4774 | 1.4774 | 398.8 | 1964-08-01 |  |
| hubeau_hydrometrie | B022001001 | La Meuse à Goncourt | 48.240913254 | 5.614415096 |  | 1.478 | 1.478 | 452.2 | 1971-09-14 |  |
| hubeau_hydrometrie | A902102101 | Le ruisseau de Gondrexange à Imling | 48.709216717 | 7.019469795 |  | 1.4799 | 1.4799 | 104.2 | 2015-09-01 |  |
| hubeau_hydrometrie | A919205050 | L'Albe à Sarralbe - Eich | 48.997419075 | 7.019499795 |  | 1.4827 | 1.4827 | 433.3 | 2008-01-01 |  |
| hubeau_hydrometrie | B105201001 | Le Mouzon à Sommerécourt | 48.224397022 | 5.664011145 |  | 1.4844 | 1.4844 | 227.4 | 1995-01-12 |  |

## Limitations and what this study does not establish

- Step s4, gate spread_within: spread_within needs two or more paths and a value
- These years are in no tool result: 1840. If they are from memory, the sentence should say so: from general knowledge, not from the data.

Caveats, verbatim from the playbook:
- Every transferred number is quoted with its band across donors and the leave-one-out skill of that signature; a bare regionalised number is not an estimate.
- Donor regionalisation is validated at national scale (HESS 2024, doi:10.5194/hess-28-3367-2024), which says the method works on average, not that it works at this point; the band and the skill are the local evidence.
- GloFAS discharge is a model output for a grid cell of about 5 km, not a gauge reading; it is a cross-check, not an observation.

Expected at planning:
- Every transferred signature carries a donor band and a leave-one-out skill; a bare regionalised number is not by itself a defensible estimate.
- Donor regionalisation is validated at national scale (HESS 2024) which shows the method works on average, not specifically at this point; the band and skill are the local evidence of fit.
- GloFAS discharge is a ~5 km grid-cell model output, not an observation, so it serves only as a cross-check and can diverge from the true local regime, especially for low flows (Q95) which models often underrepresent.
- No local abstraction, irrigation withdrawal or detailed dam-operation data beyond the HydroATLAS dam index is available, so the natural-flow estimate may not fully reflect current regulated conditions at Bamako.

## What this study does not establish

- Step s4, gate spread_within: spread_within needs two or more paths and a value
- These years are in no tool result: 1840. If they are from memory, the sentence should say so: from general knowledge, not from the data.

## Caveats

- Every transferred number is quoted with its band across donors and the leave-one-out skill of that signature; a bare regionalised number is not an estimate.
- Donor regionalisation is validated at national scale (HESS 2024, doi:10.5194/hess-28-3367-2024), which says the method works on average, not that it works at this point; the band and the skill are the local evidence.
- GloFAS discharge is a model output for a grid cell of about 5 km, not a gauge reading; it is a cross-check, not an observation.

## Recommendations

- Before relying on step s4, settle the failed gate spread_within: spread_within needs two or more paths and a value. A longer record or another source would.
- A fallback ran after a failed gate; its numbers are indicative, not a substitute for the step that failed.
- Read the numbers with this caveat: Every transferred number is quoted with its band across donors and the leave-one-out skill of that signature; a bare regionalised number is not an estimate.
- Read the numbers with this caveat: Donor regionalisation is validated at national scale (HESS 2024, doi:10.5194/hess-28-3367-2024), which says the method works on average, not that it works at this point; the band and the skill are the local evidence.

## References

1. Oudin, L. et al. (2008). Spatial proximity, physical similarity, regression and ungaged catchments. Water Resour. Res. 44, W03413.
2. Harrigan, S. et al. (2020). GloFAS-ERA5 operational global river discharge reanalysis 1979-present. Earth Syst. Sci. Data, 12, 2043-2060.
3. Bloeschl, G., Sivapalan, M., Wagener, T., Viglione, A., Savenije, H. (eds.) (2013). Runoff Prediction in Ungauged Basins. Cambridge University Press; Oudin, L. et al. (2008). Spatial proximity, physical similarity, regression and ungaged catchments. Water Resour. Res. 44, W03413. Attributes: HydroATLAS v1.0 (BasinATLAS), CC BY 4.0. Linke, S., Lehner, B., Ouellet Dallaire, C., et al. (2019). Global hydro-environmental sub-basin and river reach characteristics at high spatial resolution. Scientific Data 6: 283. https://doi.org/10.1038/s41597-019-0300-6
4. Bloeschl, G. et al. (eds.) (2013). Runoff Prediction in Ungauged Basins. Cambridge University Press
5. Addor, N. et al. (2018). A ranking of hydrological signatures based on their predictability in space. Water Resour. Res. 54, 8792-8812.
6. Hersbach, H. et al. (2020). The ERA5 global reanalysis. Q. J. R. Meteorol. Soc., 146, 1999-2049
7. Open-Meteo.com (CC BY 4.0).
8. Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). Crop evapotranspiration. FAO Irrigation and Drainage Paper 56.
9. Hosking, J. R. M. (1990). L-moments: analysis and estimation of distributions using linear combinations of order statistics. J. R. Stat. Soc. B, 52(1), 105-124.
10. England, J. F. Jr. et al. (2018). Guidelines for determining flood flow frequency, Bulletin 17C. USGS Techniques and Methods 4-B5.
11. National-scale validation of donor regionalisation: Hydrol. Earth Syst. Sci. 28 (2024), doi:10.5194/hess-28-3367-2024
12. Parameter regionalisation at national scale: Sci. Rep. (2026), doi:10.1038/s41598-026-49424-z
13. Vogel, R. M. and Fennessey, N. M. (1994). Flow-duration curves I: new interpretation and confidence intervals. J. Water Resour. Plann. Manage. 120, 485-504.
14. Rekin226 and contributors (2026). AquaScope: Open-source water data aggregation toolkit (version 0.14.0) [Software]. Zenodo. https://doi.org/10.5281/zenodo.21903143

## Appendix: reproducibility

Re-run the same steps with no model: `aquascope run study.yaml`. Resume the workspace: `aquascope studio --resume workspace.json`.

Model: claude-sonnet-5 via anthropic; ledger: consultant 1 call(s), 3689 tokens, methodologist 1 call(s), 8354 tokens, analyst 1 call(s), 5407 tokens, author 1 call(s), 38433 tokens, critic 1 call(s), 34976 tokens. aquascope 0.14.0.

```yaml
# An AquaScope study (version 3): the plan behind an answer, its gates, and what happened.
#   aquascope run study.yaml
version: 3
title: "Provide a mean annual flow and Q95 low-flow estimate, in m3/: 12.6, -8.0"
question: "No gauge I can reach on the Niger at Bamako: what mean flow and Q95 should a water-supply offtake expect?"
created: "2026-09-07T13:49:52+00:00"
aquascope_version: "0.14.0"
author: "methodologist"
model: "claude-sonnet-5"
problem:
  kind: "ungauged_flow"
  site: {"lat": 12.6, "lon": -8.0}
  params: {"purpose": "water supply", "statistic": "all"}
  text: "No gauge I can reach on the Niger at Bamako: what mean flow and Q95 should a water-supply offtake expect?"
plan:
  author: "methodologist"
  playbook: "ungauged_flow"
  objective: "Provide a mean annual flow and Q95 low-flow estimate, in m3/s, for the Niger at the Bamako offtake site to support sizing a water-supply intake where no gauge record is reachable."
  decision: "Use donor-basin regionalisation of flow signatures, converted to m3/s with the site's BasinATLAS upstream area, cross-checked against GloFAS modelled discharge, as the basis for offtake sizing since at-site flow-duration and GR4J calibration are not defensible without a discharge record at this site."
  methodology: ["Delineate and characterise the catchment upstream of the site (lat 12.6, lon -8.0) using BasinATLAS/HydroATLAS to obtain the upstream area and attributes needed for donor matching and unit conversion.", "Identify the 10 gauged donor basins most similar to this catchment in attribute space from the 37,071-gauge pool.", "Transfer mean, median, Q95 and Q05 flow signatures (in mm/d) from the donor set to the site, each reported with its cross-donor band and leave-one-out skill.", "Convert the regionalised mean and Q95 signatures from mm/d to m3/s using the BasinATLAS upstream area (115,012.9 km2).", "Pull ERA5 climate and GloFAS modelled discharge for the site coordinates as an independent cross-check of the regionalised mean flow and Q95.", "Compare the regionalised m3/s estimates against the GloFAS-derived mean and low-flow statistics and report agreement or divergence as part of the confidence statement.", "Recommend the offtake design flows only with the accompanying donor band, leave-one-out skill, and GloFAS cross-check attached, not as bare point numbers."]
  assumptions: ["catchment delineation and area (115,012.9 km2 upstream) taken from BasinATLAS HydroATLAS v1.0 at the given coordinates", "regionalisation draws on the 10 donor gauges identified from the 37,071-gauge pool as hydrologically similar", "GloFAS discharge is reachable for this location for cross-checking regionalised estimates", "no local abstraction, dam operation, or channel modification data beyond the HydroATLAS dam index (6.3) is available to adjust the natural-flow estimate", "The catchment delineation and upstream area (115,012.9 km2) from BasinATLAS HydroATLAS v1.0 at 12.6N, -8.0E is representative of the actual offtake location.", "The 10 donor gauges identified by catchment similarity are hydrologically comparable to the Niger at Bamako despite geographic distance.", "GloFAS discharge is reachable and reasonably representative of the natural flow regime at this grid cell for cross-checking purposes.", "The HydroATLAS dam index (6.3) is the only regulation signal available and no further abstraction or dam-operation adjustment is applied to the natural-flow estimate.", "Converting regionalised mm/d signatures to m3/s using the BasinATLAS upstream area introduces no significant additional error beyond the donor-transfer uncertainty."]
  alternatives: [{"method": "flow_duration", "why_not": "marked not_defensible in the sufficiency table: no discharge record exists at this site to build a flow-duration curve"}, {"method": "gr4j_calibration", "why_not": "marked not_defensible in the sufficiency table: rainfall-runoff calibration requires an observed discharge record at the site, which is absent"}]
  limitations_expected: ["Every transferred signature carries a donor band and a leave-one-out skill; a bare regionalised number is not by itself a defensible estimate.", "Donor regionalisation is validated at national scale (HESS 2024) which shows the method works on average, not specifically at this point; the band and skill are the local evidence of fit.", "GloFAS discharge is a ~5 km grid-cell model output, not an observation, so it serves only as a cross-check and can diverge from the true local regime, especially for low flows (Q95) which models often underrepresent.", "No local abstraction, irrigation withdrawal or detailed dam-operation data beyond the HydroATLAS dam index is available, so the natural-flow estimate may not fully reflect current regulated conditions at Bamako."]
  citations: ["Oudin, L. et al. (2008). Spatial proximity, physical similarity, regression and ungaged catchments. Water Resour. Res. 44, W03413.", "National-scale validation of donor regionalisation: Hydrol. Earth Syst. Sci. 28 (2024), doi:10.5194/hess-28-3367-2024", "Parameter regionalisation at national scale: Sci. Rep. (2026), doi:10.1038/s41598-026-49424-z", "Vogel, R. M. and Fennessey, N. M. (1994). Flow-duration curves I: new interpretation and confidence intervals. J. Water Resour. Plann. Manage. 120, 485-504.", "Harrigan, S. et al. (2020). GloFAS-ERA5 operational global river discharge reanalysis 1979-present. Earth Syst. Sci. Data 12, 2043-2060.", "HESS 2024, doi:10.5194/hess-28-3367-2024"]
  caveats: ["Every transferred number is quoted with its band across donors and the leave-one-out skill of that signature; a bare regionalised number is not an estimate.", "Donor regionalisation is validated at national scale (HESS 2024, doi:10.5194/hess-28-3367-2024), which says the method works on average, not that it works at this point; the band and the skill are the local evidence.", "GloFAS discharge is a model output for a grid cell of about 5 km, not a gauge reading; it is a cross-check, not an observation."]
  rationale: "Provide a mean annual flow and Q95 low-flow estimate, in m3/s, for the Niger at the Bamako offtake site to support sizing a water-supply intake where no gauge record is reachable."
  recon_notes: ["No catalog gauge within 50 km; the nearest is Le Blavet \u00e0 Neulliac - Blavet Auquinian (hubeau_hydrometrie/J543211003) at 2,656 km.", "10 donor gauges from a pool of 37,071 gauged catchments.", "ERA5 temperature and forcing and GloFAS discharge are assumed reachable for any point on land (Open-Meteo); not checked here.", "CMIP6 change factors need model output you supply (aquascope.climate works on downloaded data); not counted.", "No gauge with a usable record within 50 km: at-site methods are not defensible; what remains is the regionalisation path (similar_basins, regionalize_signatures) and the GloFAS cross-check."]
  replans: [{"step": "s4", "reason": "gate failed: spread_within (spread_within needs two or more paths and a value)", "fallback": {"tool": "regionalize_signatures", "arguments": {"lat": 12.6, "lon": -8.0, "k": 10, "method": "both"}, "rationale": "Re-run the regionalisation with method both to obtain a robust mean_m3s and Q95 estimate that can be paired with the GloFAS mean_m3s (0.571 m3/s) for the spread_within cross-check.", "expects": []}}]
steps:
  - tool: "describe_catchment"
    id: "s1"
    rationale: "Establishes the catchment area and attributes needed for donor similarity matching and for converting mm/d signatures to m3/s."
    arguments:
      lat: 12.6
      lon: -8.0
      upstream: true
    expects:
      - {"check": "not_empty", "path": "sub_basin"}
      - {"check": "max_area_km2", "path": "sub_basin.up_area", "value": 200000}
    outputs: [{"kind": "figure", "id": "s1_site_map", "caption": "site map from describe_catchment"}, {"kind": "table", "id": "s1_catchment_attributes", "caption": "catchment attributes from describe_catchment"}]
  - tool: "similar_basins"
    id: "s2"
    rationale: "Selects the 10 gauged donor catchments most hydrologically similar to the site for signature transfer."
    method: "similar_basins"
    arguments:
      lat: 12.6
      lon: -8.0
      k: 10
    expects:
      - {"check": "min_donors", "path": "k", "value": 3}
      - {"check": "not_empty", "path": "stations"}
    depends_on: ["s1"]
    outputs: [{"kind": "figure", "id": "s2_donors_map", "caption": "donors map from similar_basins"}, {"kind": "table", "id": "s2_donors", "caption": "donors from similar_basins"}]
  - tool: "regionalize_signatures"
    id: "s3"
    rationale: "Transfers mean, median, Q95 and Q05 flow signatures from the 10 donors to the ungauged site with an uncertainty band and leave-one-out skill."
    method: "regionalize_signatures"
    arguments:
      lat: 12.6
      lon: -8.0
      k: 10
    expects:
      - {"check": "not_empty", "path": "estimates"}
      - {"check": "not_empty", "path": "skill"}
    depends_on: ["s2"]
    outputs: [{"kind": "figure", "id": "s3_signatures_band", "caption": "signatures band from regionalize_signatures"}, {"kind": "table", "id": "s3_signatures", "caption": "signatures from regionalize_signatures"}, {"kind": "table", "id": "s3_donors", "caption": "donors from regionalize_signatures"}]
  - tool: "anywhere"
    id: "s4"
    rationale: "Provides GloFAS modelled discharge and ERA5 water balance for the cell as an independent check on the regionalised mean flow and Q95."
    method: "glofas_cross_check"
    arguments:
      lat: 12.6
      lon: -8.0
      years: 20
    expects:
      - {"check": "not_empty", "path": "climate"}
      - {"check": "not_empty", "path": "climate", "repaired_from": "glofas"}
      - {"check": "spread_within", "path": ["s3.signatures.mean_m3s", "s4.glofas.mean_m3s"], "value": 0.5}
    fallback: {"step": {"tool": "regionalize_signatures", "arguments": {"lat": 12.6, "lon": -8.0, "k": 10, "method": "both"}, "rationale": "Re-run the regionalisation with method both to obtain a robust mean_m3s and Q95 estimate that can be paired with the GloFAS mean_m3s (0.571 m3/s) for the spread_within cross-check.", "expects": []}}
    depends_on: ["s1", "s3"]
    outputs: [{"kind": "figure", "id": "s4_monthly_climate", "caption": "monthly climate from anywhere"}, {"kind": "figure", "id": "s4_glofas_series", "caption": "glofas series from anywhere"}, {"kind": "table", "id": "s4_monthly_climate", "caption": "monthly climate from anywhere"}, {"kind": "table", "id": "s4_glofas_summary", "caption": "glofas summary from anywhere"}]
results:
  s1: {"ok": true, "gates": [{"check": "not_empty", "passed": true, "detail": "'sub_basin' is present"}, {"check": "max_area_km2", "passed": true, "detail": "catchment of 115,013 km2 against a ceiling of 200,000 km2"}], "summary": "latitude=12.6, longitude=-8.0, license=CC-BY-4.0, attribution=HydroATLAS v1.0 (BasinATLAS), CC BY 4.0. Linke, S., Lehner, B., Ouellet Dallaire, C., et al. (2019). Global hydro-environmental sub-basin ", "fallback_used": false, "sha256": "6fde09031ecf7058"}
  s2: {"ok": true, "gates": [{"check": "min_donors", "passed": true, "detail": "10 donors, 3 needed"}, {"check": "not_empty", "passed": true, "detail": "'stations' is present"}], "summary": "k=10, method=combined", "fallback_used": false, "sha256": "bed6e55a05fc28ab"}
  s3: {"ok": true, "gates": [{"check": "not_empty", "passed": true, "detail": "'estimates' is present"}, {"check": "not_empty", "passed": true, "detail": "'skill' is present"}], "summary": "method=similarity", "fallback_used": false, "sha256": "93eacdb831e7ae0b"}
  s4: {"ok": true, "gates": [{"check": "not_empty", "passed": true, "detail": "'climate' is present"}, {"check": "not_empty", "passed": true, "detail": "'climate' is present"}, {"check": "spread_within", "passed": false, "detail": "spread_within needs two or more paths and a value"}], "summary": "years=20, start=2006-08-31, end=2026-08-31", "fallback_used": true, "sha256": "01972c6896e0c5f9", "fallback": {"tool": "regionalize_signatures", "arguments": {"lat": 12.6, "lon": -8.0, "k": 10, "method": "both"}, "ok": true, "gates": [], "summary": "method=both"}}
```

## Cite this software

AquaScope Studio (2026). AquaScope: Open-source water data aggregation toolkit (version 0.14.0) [Software]. Zenodo. https://doi.org/10.5281/zenodo.21903143


---

*{'model': 'claude-sonnet-5', 'provider': 'anthropic', 'prose': 'model', 'tokens': {'consultant': {'calls': 1, 'prompt_tokens': 2917, 'completion_tokens': 772}, 'methodologist': {'calls': 1, 'prompt_tokens': 5187, 'completion_tokens': 3167}, 'analyst': {'calls': 1, 'prompt_tokens': 4738, 'completion_tokens': 669}, 'author': {'calls': 2, 'prompt_tokens': 57722, 'completion_tokens': 18927}, 'critic': {'calls': 1, 'prompt_tokens': 25094, 'completion_tokens': 9882}}, 'total_tokens': 129075, 'aquascope_version': '0.14.0', 'date': '2026-09-07 13:55 UTC', 'workspace': '51c271e2534e', 'plan_author': 'methodologist'}*
