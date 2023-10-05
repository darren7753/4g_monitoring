import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import os

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
    #             padding-top: 1rem;
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
            border: 1px solid #e0e0e2 !important;
        </style>
    """
    st.markdown(st_expander, unsafe_allow_html=True)

    st.markdown("""
        <style type="text/css">
        div[data-testid="stHorizontalBlock"] > div {
            border: 1.5px solid #e0e0e2;
            padding: 10px;
            margin: -5px;
            border-radius: 10px;
            background: transparent;
        }
        </style>
    """, unsafe_allow_html=True)

    # st.markdown(f"<h1 style='text-align: center;'>4G Monitoring - TSEL EID</h1>", unsafe_allow_html=True)

    # col1, col2 = st.columns(2)
    # with col1:
    #     site_id = st.text_input(label="Site ID", value="saa108", key="site_id_dwm")

    # with col2:
    #     band = st.multiselect(label="Band", options=["L1800", "L2100", "L2300", "L900"], default=["L1800", "L2100", "L2300", "L900"], key="band_dwm")

    # col1, col2, col3 = st.columns(3)
    # with col1:
    #     period = st.selectbox(label="Period", options=["Daily", "Weekly", "Monthly"], index=0, key="period_dwm")

    # with col2:
    #     start_date = st.date_input(label="Start Date", value=datetime.date(2023, 7, 1), key="start_date_dwm")

    # with col3:
    #     today = datetime.datetime.now() + datetime.timedelta(hours=7)
    #     today = datetime.datetime.now()
    #     end_date = st.date_input(label="End Date", value=today.date(), key="end_date_dwm")

    site_id = st.session_state.site_id_dwm
    band = st.session_state.band_dwm
    period = st.session_state.period_dwm
    start_date = st.session_state.start_date_dwm
    end_date = st.session_state.end_date_dwm

    # Cache for fetching data from GBQ
    @st.cache_data()
    def fetch_data(query, project_id):
        # with open("encryption_key_bigquery.key", "rb") as key_file:
        #     key = key_file.read()
        key = os.environ.get("BIGQUERY_KEY")
        cipher = Fernet(key)

        with open("encrypted_credentials_bigquery.enc", "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()

        decrypted_data = cipher.decrypt(encrypted_data)

        credentials = Credentials.from_service_account_info(eval(decrypted_data.decode()))
        return pd.read_gbq(query, project_id=project_id, credentials=credentials)

    # Cache for processing the data
    @st.cache_data()
    def process_data(df):
        df["DATE_ID"] = pd.to_datetime(df["DATE_ID"])
        df["LTE_CSFB_SR"] = 100 - df["LTE_CSFB_SR"]
        df["Downlink_Traffic_Volume"] = df["Downlink_Traffic_Volume"] / 1000
        df["Uplink_Traffic_Volume"] = df["Uplink_Traffic_Volume"] / 1000
        df["Total_Traffic_Volume"] = df["Total_Traffic_Volume"] / 1000
        return df

    if len(site_id) == 6:
        target_table = "monitoring_396408.tsel_nms"
        project_id = "monitoring-396408"
        job_location = "asia-southeast2"

        bands_str = ",".join([f"'{b}'" for b in band])

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
            WHERE
                Band IN UNNEST([{bands_str}])
            ORDER BY
                DATE_ID,
                EUTRANCELLFDD;
        """

        df = fetch_data(query, project_id)
        df = process_data(df)

        st.markdown(f"<h3>Data Overview</h3>", unsafe_allow_html=True)
        with st.expander("Click here to view the data overview"):
            st.dataframe(df, height=250)

            def convert_df(df):
                return df.to_csv().encode("utf-8")
            
            csv = convert_df(df)

            st.download_button(
                label="Download data as CSV",
                data=csv,
                file_name="data.csv",
                mime="text/csv"
            )

        if period == "Daily":
            resample = "D"
        elif period == "Weekly":
            resample = "W"
        else:
            resample = "M"

        # ------------------------------------------------------------------Row 1------------------------------------------------------------------
        plot_title_color = "#9598a6"

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Site</p>
            """, unsafe_allow_html=True)

            df1 = df.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df1,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band"
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Site</p>
            """, unsafe_allow_html=True)

            df2 = df.set_index("DATE_ID")["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Total_Traffic_Volume",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 2------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df1,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df2,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df3,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 3------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["Band"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="Band",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 4------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 5------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df1,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df2,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Total_Traffic_Volume"].resample(resample).sum().reset_index()
            fig = px.area(
                df3,
                x="DATE_ID",
                y="Total_Traffic_Volume",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 6------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 3</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="DL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="DL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="DL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 7------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Average_CQI_nonHOME"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Average_CQI_nonHOME",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Average_CQI_nonHOME"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Average_CQI_nonHOME",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Average_CQI_nonHOME"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Average_CQI_nonHOME",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 8------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["SE_2"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="SE_2",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["SE_2"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="SE_2",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["SE_2"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="SE_2",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 9------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Radio_Network_Availability_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Radio_Network_Availability_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Radio_Network_Availability_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Radio_Network_Availability_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Radio_Network_Availability_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Radio_Network_Availability_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 10------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["RRC_Setup_Success_Rate_Service"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="RRC_Setup_Success_Rate_Service",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["RRC_Setup_Success_Rate_Service"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="RRC_Setup_Success_Rate_Service",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["RRC_Setup_Success_Rate_Service"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="RRC_Setup_Success_Rate_Service",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 11------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["ERAB_Setup_Success_Rate_All"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="ERAB_Setup_Success_Rate_All",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["ERAB_Setup_Success_Rate_All"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="ERAB_Setup_Success_Rate_All",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["ERAB_Setup_Success_Rate_All"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="ERAB_Setup_Success_Rate_All",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 12------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Setup_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Session_Setup_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Setup_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Session_Setup_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Setup_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Session_Setup_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 13------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Abnormal_Release"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Session_Abnormal_Release",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Abnormal_Release"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Session_Abnormal_Release",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Session_Abnormal_Release"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Session_Abnormal_Release",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 14------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Intra_Frequency_Handover_Out_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="Intra_Frequency_Handover_Out_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Intra_Frequency_Handover_Out_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="Intra_Frequency_Handover_Out_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["Intra_Frequency_Handover_Out_Success_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="Intra_Frequency_Handover_Out_Success_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 15------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["inter_freq_HO"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="inter_freq_HO",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["inter_freq_HO"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="inter_freq_HO",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["inter_freq_HO"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="inter_freq_HO",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 16------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_RSSI_dbm"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="UL_RSSI_dbm",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_RSSI_dbm"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="UL_RSSI_dbm",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_RSSI_dbm"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="UL_RSSI_dbm",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 17------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="UL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="UL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["UL_Resource_Block_Utilizing_Rate"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="UL_Resource_Block_Utilizing_Rate",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 18------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_PDCP_User_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="DL_PDCP_User_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_PDCP_User_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="DL_PDCP_User_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["DL_PDCP_User_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="DL_PDCP_User_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 19------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["User_Uplink_Average_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="User_Uplink_Average_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["User_Uplink_Average_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="User_Uplink_Average_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["User_Uplink_Average_Throughput"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="User_Uplink_Average_Throughput",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 20------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 1</p>
            """, unsafe_allow_html=True)

            df1 = df[df["Sector"] == "1"]
            df1 = df1.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["LTE_CSFB_SR"].resample(resample).mean().reset_index()
            fig = px.line(
                df1,
                x="DATE_ID",
                y="LTE_CSFB_SR",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 2</p>
            """, unsafe_allow_html=True)

            df2 = df[df["Sector"] == "2"]
            df2 = df2.groupby(["EUTRANCELLFDD", "DATE_ID"])["LTE_CSFB_SR"].mean().reset_index()
            df2 = df2.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["LTE_CSFB_SR"].resample(resample).mean().reset_index()
            fig = px.line(
                df2,
                x="DATE_ID",
                y="LTE_CSFB_SR",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 3</p>
            """, unsafe_allow_html=True)

            df3 = df[df["Sector"] == "3"]
            df3 = df3.set_index("DATE_ID").groupby(["EUTRANCELLFDD"])["LTE_CSFB_SR"].resample(resample).mean().reset_index()
            fig = px.line(
                df3,
                x="DATE_ID",
                y="LTE_CSFB_SR",
                color="EUTRANCELLFDD",
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.35,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)