from dash import Dash, dcc, html, Input, Output
import dash
import plotly.express as px
import pandas as pd
import json
import os
import dash_bootstrap_components as dbc
from dash_bootstrap_templates import load_figure_template

##################### SETUP #####################

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "..", "data", "processed", "processed.csv")

df = pd.read_csv(CSV_PATH, parse_dates=["date"])
df = df[df["region"] != "whole_denmark"]

GEOJSON_PATH = os.path.join(BASE_DIR, "..", "data", "processed", "dk.json")
with open(GEOJSON_PATH, encoding="utf-8") as f:
    dk_geo = json.load(f)

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.MATERIA],
)
load_figure_template("MATERIA")

server = app.server

##################### DATA #####################

dominant = df.loc[df.groupby(["region", "date"])["pct"].idxmax()][
    ["region", "date", "variant_group"]
]

dominant = dominant[dominant["region"] != "whole_denmark"]

mapping = {
    "copenhagen": "Hovedstaden",
    "sjælland": "Sjælland",
    "nordjylland": "Nordjylland",
    "midtjylland": "Midtjylland",
    "syddanmark": "Syddanmark",
}

COLOR_MAP = {
    "Alpha": "#1f77b4",
    "D614G": "#ff7f0e",
    "EU1": "#2ca02c",
    "Mink-associated": "#d62728",
    "Other": "#9467bd",
}

dominant["region_geo"] = dominant["region"].map(mapping)

# Get every unique date in the dataset
slider_dates = sorted(df["date"].unique())

##################### LAYOUT #####################

app.layout = dbc.Container(
    [
        # ---------- Title ----------
        dbc.Row(
            dbc.Col(
                html.H1(
                    "Danish COVID Variant Dashboard",
                    className="text-center my-4",
                )
            )
        ),
        # ---------- Sidebar + Graphs ----------
        dbc.Row(
            [
                # ---------- Sidebar ----------
                dbc.Col(
                    html.Div(
                        [
                            html.H4("Controls", className="mb-4"),
                            html.Label("Region"),
                            dcc.Dropdown(
                                id="region_dropdown",
                                options=[
                                    {
                                        "label": r.title(),
                                        "value": r,
                                    }
                                    for r in sorted(df["region"].unique())
                                ],
                                value="copenhagen",
                                clearable=False,
                            ),
                            html.Br(),
                            html.Label("Selected date"),
                            html.Div(
                                id="selected-date",
                                className="fw-bold mb-3",
                            ),
                            dcc.Slider(
                                id="date_slider",
                                min=0,
                                max=len(slider_dates) - 1,
                                value=0,
                                step=1,
                                marks={
                                    0: slider_dates[0].strftime("%Y-%m-%d"),
                                    len(slider_dates)
                                    - 1: slider_dates[-1].strftime("%Y-%m-%d"),
                                },
                                tooltip={
                                    "always_visible": False,
                                },
                                updatemode="drag",
                                allow_direct_input=False,
                            ),
                        ],
                        style={
                            "backgroundColor": "#f8f9fa",
                            "padding": "20px",
                            "borderRadius": "10px",
                            "boxShadow": "0 2px 6px rgba(0,0,0,0.15)",
                            "height": "100%",
                        },
                    ),
                    width=3,
                ),
                # ---------- Right side ----------
                dbc.Col(
                    [
                        # Top row: map + stacked area
                        dbc.Row(
                            [
                                dbc.Col(
                                    dcc.Graph(
                                        id="map",
                                        style={"height": "500px"},
                                    ),
                                    width=6,
                                ),
                                dbc.Col(
                                    dcc.Graph(
                                        id="stacked_area_graph",
                                        style={"height": "500px"},
                                    ),
                                    width=6,
                                ),
                            ]
                        ),
                        dbc.Row(
                            dbc.Col(
                                dcc.Graph(
                                    id="line_graph",
                                    style={"height": "600px"},
                                ),
                                width=12,
                            ),
                            className="mt-0",
                        ),
                    ],
                    width=9,
                ),
            ]
        ),
    ],
    fluid=True,
)

##################### SLIDER CALLBACK  #####################


@app.callback(
    Output("selected-date", "children"),
    Input("date_slider", "value"),
)
def update_selected_date(slider_value):
    return slider_dates[slider_value].strftime("%Y-%m-%d")


##################### CHOROPLETH #####################


def make_map(df_subset):
    fig = px.choropleth(
        df_subset,
        geojson=dk_geo,
        locations="region_geo",
        featureidkey="properties.name",
        color="variant_group",
        color_discrete_map=COLOR_MAP,
    )

    fig.update_geos(fitbounds="locations", visible=False)

    fig.update_layout(
        margin=dict(
            l=5,
            r=5,
            t=10,
            b=5,
        )
    )

    return fig


@app.callback(
    Output("map", "figure"),
    Input("date_slider", "value"),
)
def update_map(slider_value):
    if slider_value is None:
        return dash.no_update

    selected_date = slider_dates[slider_value]

    df_subset = dominant[dominant["date"] == selected_date]

    return make_map(df_subset)


##################### STACKED AREA #####################


@app.callback(
    Output("stacked_area_graph", "figure"),
    Input("region_dropdown", "value"),
    Input("date_slider", "value"),
)
def update_stacked(region_value, slider_value):
    if slider_value is None:
        return dash.no_update

    # Slider position corresponds to a month
    selected_date = slider_dates[slider_value]

    # Filter selected region
    df_region = df[df["region"] == region_value]

    # Find range where real data exists
    mask = df_region["positive"] > 0
    first_real = df_region.loc[mask, "date"].min()
    last_real = df_region.loc[mask, "date"].max()

    # Find the last observation within the selected month or earlier
    actual_end = df_region.loc[df_region["date"] <= selected_date, "date"].max()

    if pd.isna(actual_end):
        actual_end = first_real

    # Build counts table
    counts = (
        df_region.groupby(["date", "variant_group"])["positive"]
        .sum()
        .unstack(fill_value=0)
    )

    # Normalize to proportions
    pivot = counts.div(counts.sum(axis=1), axis=0)

    # Keep only real data range
    pivot = pivot.loc[first_real:last_real]

    # Convert back to long format
    df_long = pivot.reset_index().melt(
        id_vars="date",
        var_name="variant_group",
        value_name="pct",
    )

    # Only include data up to slider date
    df_long = df_long[df_long["date"] <= actual_end]

    # Plot
    fig = px.area(
        df_long,
        x="date",
        y="pct",
        color="variant_group",
        groupnorm="fraction",
        color_discrete_map=COLOR_MAP,
    )

    # Fixed left edge, moving right edge
    fig.update_xaxes(range=[first_real, actual_end])

    fig.update_yaxes(range=[0, 1])

    fig.update_layout(
        margin=dict(
            l=5,
            r=5,
            t=5,
            b=5,
        )
    )

    return fig


##################### LINE GRAPH #####################


##################### DEBUG #####################


def debug_all():
    print("\n================ DEBUG START ================\n")

    print("CSV regions:")
    print(sorted(df["region"].unique()))
    print()

    print("GeoJSON regions:")
    geo_regions = [f["properties"]["name"] for f in dk_geo["features"]]
    print(sorted(geo_regions))
    print()

    print("Mapping keys vs CSV keys:")
    print("Mapping keys:", sorted(mapping.keys()))
    print("CSV keys:    ", sorted(df["region"].unique()))
    print()

    print("Mapping values vs GeoJSON names:")
    print("Mapping values:", sorted(mapping.values()))
    print("GeoJSON names: ", sorted(geo_regions))
    print()

    print("dominant['region_geo'] unique values:")
    print(sorted(dominant["region_geo"].unique()))
    print()


# Run diagnostics on startup
debug_all()

##################### RUN #####################

if __name__ == "__main__":
    app.run(debug=False)
