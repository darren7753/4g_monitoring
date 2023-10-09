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

    site_id_dwm = st.session_state.site_id_dwm
    band_dwm = st.session_state.band_dwm
    period_dwm = st.session_state.period_dwm
    start_date_dwm = st.session_state.start_date_dwm
    end_date_dwm = st.session_state.end_date_dwm

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

    if len(site_id_dwm) == 6:
        target_table = "monitoring_396408.tsel_nms"
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
                    LOWER(EUTRANCELLFDD) LIKE '%{site_id_dwm.lower()}%'
                    AND DATE_ID BETWEEN '{start_date_dwm}' AND '{end_date_dwm}'
            )

            SELECT
                *
            FROM RAW
            ORDER BY
                DATE_ID,
                EUTRANCELLFDD;
        """

        df_polars = fetch_data(query, project_id)

        df_polars = df_polars.with_columns(df_polars["DATE_ID"].cast(pl.Date))
        df_polars = df_polars.with_columns([
            (100 - df_polars["LTE_CSFB_SR"]).alias("LTE_CSFB_SR"),
            (df_polars["Downlink_Traffic_Volume"] / 1000).alias("Downlink_Traffic_Volume"),
            (df_polars["Uplink_Traffic_Volume"] / 1000).alias("Uplink_Traffic_Volume"),
            (df_polars["Total_Traffic_Volume"] / 1000).alias("Total_Traffic_Volume")
        ])
        df_polars = df_polars.filter(df_polars["Band"].is_in(band_dwm))

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


        if period_dwm == "Daily":
            dtick = 3*24*60*60*1000
            every = "1d"
        elif period_dwm == "Weekly":
            dtick = 7*24*60*60*1000
            every = "1w"
        else:
            dtick = "M1"
            every = "1mo"

        # ------------------------------------------------------------------Row 1------------------------------------------------------------------
        plot_title_color = "#FFF"

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Site</p>
            """, unsafe_allow_html=True)

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
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.5,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Site</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.sort("DATE_ID")
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every).agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
            )
            fig.update_layout(
                xaxis_title="",
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.5,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=300,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 2------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 3------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "Band"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="Band").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["Band"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 4------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 5------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"

            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Payload - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Total_Traffic_Volume"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).sum().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.area(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 6------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "DL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "DL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL PRB - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "DL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 7------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Average_CQI_nonHOME"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Average_CQI_nonHOME"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>CQI - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Average_CQI_nonHOME"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 8------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "SE_2"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "SE_2"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SE - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "SE_2"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 9------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Radio_Network_Availability_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Radio_Network_Availability_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>Availability - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Radio_Network_Availability_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 10------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "RRC_Setup_Success_Rate_Service"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "RRC_Setup_Success_Rate_Service"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RRCSR - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "RRC_Setup_Success_Rate_Service"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 11------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "ERAB_Setup_Success_Rate_All"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "ERAB_Setup_Success_Rate_All"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>ERABSR - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "ERAB_Setup_Success_Rate_All"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 12------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Setup_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Setup_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SSSR - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Setup_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 13------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Abnormal_Release"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Abnormal_Release"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>SAR - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Session_Abnormal_Release"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 14------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "Intra_Frequency_Handover_Out_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "Intra_Frequency_Handover_Out_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTRAFreq - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "Intra_Frequency_Handover_Out_Success_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 15------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "inter_freq_HO"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "inter_freq_HO"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>INTERFreq - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "inter_freq_HO"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 16------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "UL_RSSI_dbm"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "UL_RSSI_dbm"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>RSSI - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "UL_RSSI_dbm"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 17------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "UL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "UL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>UL PRB - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "UL_Resource_Block_Utilizing_Rate"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 18------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "DL_PDCP_User_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "DL_PDCP_User_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>DL_PDCP_User_Throughput - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "DL_PDCP_User_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 19------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "User_Uplink_Average_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "User_Uplink_Average_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>User_Uplink_Average_Throughput - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "User_Uplink_Average_Throughput"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        # ------------------------------------------------------------------Row 20------------------------------------------------------------------
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 1</p>
            """, unsafe_allow_html=True)

            target_column = "LTE_CSFB_SR"
            
            df = df_polars.filter(pl.col("Sector") == "1")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 2</p>
            """, unsafe_allow_html=True)

            target_column = "LTE_CSFB_SR"
            
            df = df_polars.filter(pl.col("Sector") == "2")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col3:
            st.markdown(f"""
            <p style='text-align: center; font-family: "Open Sans", verdana, arial, sans-serif; font-size: 14px; color: {plot_title_color};'>LTE_CSFB_SR - Sec 3</p>
            """, unsafe_allow_html=True)

            target_column = "LTE_CSFB_SR"
            
            df = df_polars.filter(pl.col("Sector") == "3")
            df = df.sort(["DATE_ID", "EUTRANCELLFDD"])
            aggregation = pl.col(target_column).mean().alias(target_column)
            df = df.group_by_dynamic("DATE_ID", every=every, by="EUTRANCELLFDD").agg(aggregation)

            first_date = df["DATE_ID"].head(1)[0]

            fig = px.line(
                df,
                x=df["DATE_ID"],
                y=df[target_column],
                color=df["EUTRANCELLFDD"],
            )
            fig.update_layout(
                xaxis_title="",
                yaxis_title=target_column,
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.8,
                    xanchor="center",
                    x=0.5
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                height=250,
                xaxis=dict(
                    tickangle=270,
                    dtick=dtick,
                    tick0=first_date,
                    tickformat="%Y-%m-%d"
                )
            )
            fig.update_traces(
                hovertemplate=f"<b>%{{x}}</b><br>{target_column}: %{{y}}<extra></extra>"
            )
            st.plotly_chart(fig, use_container_width=True)