import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import os
import polars as pl

from google.cloud import bigquery
from google.oauth2.service_account import Credentials
from cryptography.fernet import Fernet

def app():
    # st.set_page_config(
    #     page_title="4G Monitoring - TSEL EID",
    #     layout="wide"
    # )

    # reduce_header_height_style = """
    #     <style>
    #         div.block-container {
    #             padding-top: 0rem;
    #             padding-bottom: 1rem;
    #         }
    #     </style>
    # """
    # st.markdown(reduce_header_height_style, unsafe_allow_html=True)

    # hide_decoration_bar_style = """
    #     <style>
    #         header {visibility: hidden;}
    #         footer {visibility: hidden;}
    #     </style>
    # """
    # st.markdown(hide_decoration_bar_style, unsafe_allow_html=True)

    st_expander = """
        <style>
        ul.streamlit-expander {
            border: 0px solid #9598a6 !important;
        </style>
    """
    st.markdown(st_expander, unsafe_allow_html=True)

    st.markdown("""
        <style type="text/css">
        div[data-testid="stHorizontalBlock"] > div {
            border: 0.5px solid #9598a6;
            padding: 10px;
            margin: -5px;
            border-radius: 10px;
            background: transparent;
        }
        </style>
    """, unsafe_allow_html=True)

    site_id = st.session_state.site_id_hourly
    band = st.session_state.band_hourly
    period = st.session_state.period_hourly
    start_date = st.session_state.start_date_hourly
    end_date = st.session_state.end_date_hourly

    # Cache for fetching data from GBQ
    @st.cache_data()    
    def fetch_data(query, project_id):
        with open("encryption_key_bigquery.key", "rb") as key_file:
            key = key_file.read()
        # key = os.environ.get("BIGQUERY_KEY")
        cipher = Fernet(key)

        with open("encrypted_credentials_bigquery.enc", "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()

        decrypted_data = cipher.decrypt(encrypted_data)
        credentials = Credentials.from_service_account_info(eval(decrypted_data.decode()))
        client = bigquery.Client(credentials=credentials, project=project_id)

        query_job = client.query(query)
        rows = query_job.result()

        df_polars = pl.from_arrow(rows.to_arrow())        
        return df_polars

    if len(site_id) == 6:
        target_table = "monitoring_396408.tsel_nms_hourly"
        project_id = "monitoring-396408"
        job_location = "asia-southeast2"

        # bands_str = ",".join([f"'{b}'" for b in band])

        query = f"""
            WITH RAW AS (
                SELECT
                    *,
                    LEFT(EUTRANCELLFDD, 6) AS SiteID,
                    CASE 
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("AL", "EL", "IL", "ML", "SL") THEN "L1800"
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("ER", "HR", "IR", "MR") THEN "L2100"
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("ME", "MF", "IE", "IF", "MV", "VE", "VF") THEN "L2300"
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("MT", "ST") THEN "L900"
                        ELSE "Not Define"
                    END AS Band,
                    CASE 
                        WHEN RIGHT(EUTRANCELLFDD, 1) IN ('1', '4') THEN '1' 
                        WHEN RIGHT(EUTRANCELLFDD, 1) IN ('2', '5') THEN '2' 
                        WHEN RIGHT(EUTRANCELLFDD, 1) IN ('3', '6') THEN '3' 
                        ELSE "Not Define"
                    END AS Sector,
                    CASE 
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("AL", "EL", "IL", "ML", "SL") THEN CONCAT(LEFT(EUTRANCELLFDD, 6), "ML1")
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("ER", "HR", "IR", "MR") THEN CONCAT(LEFT(EUTRANCELLFDD, 6), "MR1")
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("ME", "MF", "IE", "IF", "MV", "VE", "VF") THEN CONCAT(LEFT(EUTRANCELLFDD, 6), "ME1")
                        WHEN SUBSTR(EUTRANCELLFDD, 7, 2) IN ("MT", "ST", "MM") THEN CONCAT(LEFT(EUTRANCELLFDD, 6), "MT1")
                        ELSE "Not Define"
                    END AS NEID
                FROM
                    `{project_id}.{target_table}`
                WHERE
                    LOWER(EUTRANCELLFDD) LIKE '%{site_id.lower()}%'
                    AND DATE_ID BETWEEN '{start_date}' AND '{end_date}'
            )

            SELECT
                *
            FROM RAW
            ORDER BY
                DATE_ID,
                EUTRANCELLFDD;
        """

        df_polars = fetch_data(query, project_id)

        if len(df_polars) == 0:
            st.warning("Data isn't available.")
        else:
            df_polars = df_polars.with_columns(df_polars["DATE_ID"].cast(pl.Datetime))
            df_polars = df_polars.with_columns([
                (100 - df_polars["LTE_CSFB_SR"]).alias("LTE_CSFB_SR"),
                (df_polars["DATE_ID"] + pl.duration(hours="HOUR_ID")).alias("DATE_ID")
            ])
            df_polars = df_polars.with_columns(df_polars["DATE_ID"].cast(pl.Datetime))
            df_polars = df_polars.drop("HOUR_ID")
            df_polars = df_polars.filter(df_polars["Band"].is_in(band))

            st.markdown(f"<h3>📊 Charts</h3>", unsafe_allow_html=True)
            col1 = st.columns(1)[0]
            with col1.expander("Click here to view the data overview"):
                st.dataframe(df_polars.to_pandas(), height=250)

                def convert_df_to_csv(df):
                    return df.write_csv()

                csv_data = convert_df_to_csv(df_polars)
                
                st.download_button(
                    label="Download data as CSV",
                    data=csv_data,
                    file_name="data.csv"
                )


            if period == "Hourly":
                dtick = 1*60*60*1000
                every = "1h"

            # 1st row
            col1, col2 = st.columns(2)
            with col1:
                target_column = "Total_Traffic_Volume"

                df = df_polars.sort(["DATE_ID", "Band"])
                aggregation = pl.col(target_column).sum().alias(target_column)
                df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

                first_date = df["DATE_ID"].head(1)[0]

                fig = px.area(
                    df,
                    x=df["DATE_ID"],
                    y=df[target_column],
                    color=df["Band"],
                    custom_data=[df["Band"]]
                )
                fig.update_layout(
                    title="Payload - Site",
                    title_x=0.5,
                    title_xanchor="center",
                    xaxis_title="",
                    yaxis_title=target_column,
                    legend_title_text="",
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-0.5 - 0.5,
                        xanchor="center",
                        x=0.5
                    ),
                    margin=dict(l=0, r=0, t=30, b=0),
                    height=340,
                    xaxis=dict(
                        tickangle=270,
                        dtick=dtick,
                        tick0=first_date,
                        tickformat="%Y-%m-%d %H:%M"
                    )
                )
                fig.update_traces(
                    hovertemplate=f"<b>%{{x}}</b><br><br>{target_column}: %{{y}}<br>Band: %{{customdata[0]}}<extra></extra>"
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                target_column = "Total_Traffic_Volume"

                df = df_polars.sort("DATE_ID")
                aggregation = pl.col(target_column).sum().alias(target_column)
                df = df.group_by_dynamic("DATE_ID", every=every).agg(aggregation)

                first_date = df["DATE_ID"].head(1)[0]

                fig = px.line(
                    df,
                    x=df["DATE_ID"],
                    y=df[target_column]
                )
                fig.update_layout(
                    title="Payload - Site",
                    title_x=0.5,
                    title_xanchor="center",
                    xaxis_title="",
                    yaxis_title=target_column,
                    legend_title_text="",
                    legend=dict(
                        orientation="h",
                        yanchor="top",
                        y=-0.5 - 0.5,
                        xanchor="center",
                        x=0.5
                    ),
                    margin=dict(l=0, r=0, t=30, b=0),
                    height=340,
                    xaxis=dict(
                        tickangle=270,
                        dtick=dtick,
                        tick0=first_date,
                        tickformat="%Y-%m-%d %H:%M"
                    )
                )
                fig.update_traces(
                    hovertemplate=f"<b>%{{x}}</b><br><br>{target_column}: %{{y}}<extra></extra>"
                )
                st.plotly_chart(fig, use_container_width=True)

            chart_configs = [
                # 2nd row
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 1",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "1",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 2",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "2",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 3",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "3",
                    "aggregation": "sum",
                },
                # 3rd row
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 1",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "1",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 2",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "2",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 3",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "Band",
                    "sector": "3",
                    "aggregation": "sum",
                },
                # 4th row
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 1",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 2",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "line",
                    "title": "Payload - Sec 3",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "sum",
                },
                # 5th row
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 1",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 2",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "sum",
                },
                {
                    "chart_type": "area",
                    "title": "Payload - Sec 3",
                    "target_column": "Total_Traffic_Volume",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "sum",
                },
                # 6th row
                {
                    "chart_type": "line",
                    "title": "DL PRB - Sec 1",
                    "target_column": "DL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "DL PRB - Sec 2",
                    "target_column": "DL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "DL PRB - Sec 3",
                    "target_column": "DL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 7h row
                {
                    "chart_type": "line",
                    "title": "CQI - Sec 1",
                    "target_column": "Average_CQI_nonHOME",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "CQI - Sec 2",
                    "target_column": "Average_CQI_nonHOME",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "CQI - Sec 3",
                    "target_column": "Average_CQI_nonHOME",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 8th row
                {
                    "chart_type": "line",
                    "title": "SE - Sec 1",
                    "target_column": "SE_2",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SE - Sec 2",
                    "target_column": "SE_2",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SE - Sec 3",
                    "target_column": "SE_2",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 9th row
                {
                    "chart_type": "line",
                    "title": "Availability - Sec 1",
                    "target_column": "Radio_Network_Availability_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "Availability - Sec 2",
                    "target_column": "Radio_Network_Availability_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "Availability - Sec 3",
                    "target_column": "Radio_Network_Availability_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 10th row
                {
                    "chart_type": "line",
                    "title": "RRCSR - Sec 1",
                    "target_column": "RRC_Setup_Success_Rate_Service",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "RRCSR - Sec 2",
                    "target_column": "RRC_Setup_Success_Rate_Service",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "RRCSR - Sec 3",
                    "target_column": "RRC_Setup_Success_Rate_Service",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 11th row
                {
                    "chart_type": "line",
                    "title": "ERABSR - Sec 1",
                    "target_column": "ERAB_Setup_Success_Rate_All",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "ERABSR - Sec 2",
                    "target_column": "ERAB_Setup_Success_Rate_All",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "ERABSR - Sec 3",
                    "target_column": "ERAB_Setup_Success_Rate_All",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 12nd row
                {
                    "chart_type": "line",
                    "title": "SSSR - Sec 1",
                    "target_column": "Session_Setup_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SSSR - Sec 2",
                    "target_column": "Session_Setup_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SSSR - Sec 3",
                    "target_column": "Session_Setup_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 13th row
                {
                    "chart_type": "line",
                    "title": "SAR - Sec 1",
                    "target_column": "Session_Abnormal_Release",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SAR - Sec 2",
                    "target_column": "Session_Abnormal_Release",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "SAR - Sec 3",
                    "target_column": "Session_Abnormal_Release",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 14th row
                {
                    "chart_type": "line",
                    "title": "INTRAFreq - Sec 1",
                    "target_column": "Intra_Frequency_Handover_Out_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "INTRAFreq - Sec 2",
                    "target_column": "Intra_Frequency_Handover_Out_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "INTRAFreq - Sec 3",
                    "target_column": "Intra_Frequency_Handover_Out_Success_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 15th row
                {
                    "chart_type": "line",
                    "title": "INTERFreq - Sec 1",
                    "target_column": "inter_freq_HO",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "INTERFreq - Sec 2",
                    "target_column": "inter_freq_HO",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "INTERFreq - Sec 3",
                    "target_column": "inter_freq_HO",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 16th row
                {
                    "chart_type": "line",
                    "title": "RSSI - Sec 1",
                    "target_column": "UL_RSSI_dbm",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "RSSI - Sec 2",
                    "target_column": "UL_RSSI_dbm",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "RSSI - Sec 3",
                    "target_column": "UL_RSSI_dbm",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 17th row
                {
                    "chart_type": "line",
                    "title": "UL PRB - Sec 1",
                    "target_column": "UL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "UL PRB - Sec 2",
                    "target_column": "UL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "UL PRB - Sec 3",
                    "target_column": "UL_Resource_Block_Utilizing_Rate",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 18th row
                {
                    "chart_type": "line",
                    "title": "DL_PDCP_User_Throughput - Sec 1",
                    "target_column": "DL_PDCP_User_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "DL_PDCP_User_Throughput - Sec 2",
                    "target_column": "DL_PDCP_User_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "DL_PDCP_User_Throughput - Sec 3",
                    "target_column": "DL_PDCP_User_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 19th row
                {
                    "chart_type": "line",
                    "title": "User_Uplink_Average_Throughput - Sec 1",
                    "target_column": "User_Uplink_Average_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "User_Uplink_Average_Throughput - Sec 2",
                    "target_column": "User_Uplink_Average_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "User_Uplink_Average_Throughput - Sec 3",
                    "target_column": "User_Uplink_Average_Throughput",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
                # 20th row
                {
                    "chart_type": "line",
                    "title": "LTE_CSFB_SR - Sec 1",
                    "target_column": "LTE_CSFB_SR",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "1",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "LTE_CSFB_SR - Sec 2",
                    "target_column": "LTE_CSFB_SR",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "2",
                    "aggregation": "mean",
                },
                {
                    "chart_type": "line",
                    "title": "LTE_CSFB_SR - Sec 3",
                    "target_column": "LTE_CSFB_SR",
                    "band_column": "EUTRANCELLFDD",
                    "sector": "3",
                    "aggregation": "mean",
                },
            ]

            for i in range(0, len(chart_configs), 3):
                cols = st.columns(3)

                for index, config in enumerate(chart_configs[i:i+3]):
                    with cols[index]:
                        target_column = config["target_column"]

                        df = df_polars.filter(pl.col("Sector") == config["sector"])
                        df = df.sort(["DATE_ID", config["band_column"]])

                        if config["aggregation"] == "sum":
                            aggregation = pl.col(target_column).sum().alias(target_column)
                        elif config["aggregation"] == "mean":
                            aggregation = pl.col(target_column).mean().alias(target_column)

                        df = df.group_by_dynamic("DATE_ID", every=every, by=config["band_column"]).agg(aggregation)

                        first_date = df["DATE_ID"].head(1)[0]

                        if config["chart_type"] == "area":
                            fig = px.area(
                                df,
                                x=df["DATE_ID"],
                                y=df[target_column],
                                color=df[config["band_column"]],
                                custom_data=[df[config["band_column"]]]
                            )
                        elif config["chart_type"] == "line":
                            fig = px.line(
                                df,
                                x=df["DATE_ID"],
                                y=df[target_column],
                                color=df[config["band_column"]],
                                custom_data=[df[config["band_column"]]]
                            )

                        fig.update_layout(
                            title=dict(
                                text=config["title"],
                                x=0.5,
                                xanchor="center"
                            ),
                            xaxis_title="",
                            yaxis_title=target_column,
                            legend_title_text="",
                            legend=dict(
                                orientation="h",
                                yanchor="top",
                                y=-0.8 - 0.5,
                                xanchor="center",
                                x=0.5
                            ),
                            margin=dict(l=0, r=0, t=30, b=0),
                            height=290,
                            xaxis=dict(
                                tickangle=270,
                                dtick=dtick,
                                tick0=first_date,
                                tickformat="%Y-%m-%d %H:%M"
                            )
                        )

                        if config["title"].split("-")[0].strip() in ["Availability", "INTRAFreq", "INTERFreq", "LTE_CSFB_SR", "DL PRB"]:
                            fig.update_layout(
                                yaxis_range=[None, 100]
                            )
                        if config["title"].split("-")[0].strip() in ["SSSR", "RRCSR", "ERABSR"]:
                            fig.update_layout(
                                yaxis_range=[90, 100]
                            )

                        fig.update_traces(
                            hovertemplate=f"<b>%{{x}}</b><br><br>{target_column}: %{{y}}<br>Band: %{{customdata[0]}}<extra></extra>"
                        )

                        st.plotly_chart(fig, use_container_width=True)