
import re
from io import BytesIO

import pandas as pd
import requests
import plotly.express as px
import streamlit as st


# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="전국 인구 구조 단계구분도",
    layout="wide"
)

st.title("전국 인구 구조 단계구분도")
st.caption("2015~2026년 6월 기준 · 시군구별 인구 비율")


POPULATION_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)


# 고령화율 구간: 모든 연도에서 고정
AGING_BINS = [
    float("-inf"), 19, 23, 28, 38, float("inf")
]

AGING_LABELS = [
    "19% 미만",
    "19~23% 미만",
    "23~28% 미만",
    "28~38% 미만",
    "38% 이상"
]

# 유소년 비율 구간: 모든 연도에서 고정
YOUTH_BINS = [
    float("-inf"), 6, 9, 12, 15, float("inf")
]

YOUTH_LABELS = [
    "6% 미만",
    "6~9% 미만",
    "9~12% 미만",
    "12~15% 미만",
    "15% 이상"
]

AGING_COLORS = {
    "19% 미만": "#fff5eb",
    "19~23% 미만": "#fdd49e",
    "23~28% 미만": "#fdbb84",
    "28~38% 미만": "#e34a33",
    "38% 이상": "#990000",
    "자료 없음": "#d3d3d3"
}

YOUTH_COLORS = {
    "6% 미만": "#f7fbff",
    "6~9% 미만": "#c6dbef",
    "9~12% 미만": "#6baed6",
    "12~15% 미만": "#2171b5",
    "15% 이상": "#08306b",
    "자료 없음": "#d3d3d3"
}


# ==========================================
# 2. 행정구역 코드 처리
# ==========================================
def normalize_code(value):
    """행정구역 코드를 문자열로 정리한다."""
    if pd.isna(value):
        return ""

    code = str(value).strip()

    if code.endswith(".0"):
        code = code[:-2]

    code = re.sub(r"\s+", "", code)

    if not code:
        return ""

    return code


def correct_sigungu_code(value):
    """행정구역 개편에 따른 코드 변경을 적용한다."""
    code = normalize_code(value)

    if not code:
        return ""

    # 동 코드 등 긴 코드라면 앞 5자리만 사용
    code = code[:5].zfill(5)

    # 군위군: 과거 코드 -> 현재 경계 코드
    if code == "47720":
        return "27720"

    # 강원도: 옛 시도 코드 42 -> 51
    if code.startswith("42"):
        return "51" + code[2:]

    # 전라북도: 옛 시도 코드 45 -> 52
    if code.startswith("45"):
        return "52" + code[2:]

    return code


def get_age_number(column):
    """계_65세 등의 열 이름에서 나이를 추출한다."""
    age_text = column.removeprefix("계_").strip()

    if age_text == "100세 이상":
        return 100

    match = re.fullmatch(r"(\d+)세", age_text)

    if match:
        return int(match.group(1))

    return None


# ==========================================
# 3. 인구 데이터 불러오기 및 집계
# ==========================================
@st.cache_data(ttl=3600)
def load_population():
    response = requests.get(
        POPULATION_URL,
        timeout=120
    )
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        dtype={"코드": "string"}
    )

    required = ["연도", "코드"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"인구 데이터에 필요한 열이 없습니다: {missing}"
        )

    df["연도"] = pd.to_numeric(
        df["연도"], errors="coerce"
    )

    df = df.dropna(
        subset=["연도", "코드"]
    ).copy()

    df["연도"] = df["연도"].astype(int)

    # 모든 행정구역 코드를 문자열로 처리
    df["코드"] = df["코드"].map(normalize_code)

    # 동 코드의 앞 5자리로 시군구 코드를 생성하고 보정
    df["시군구코드"] = df["코드"].map(
        correct_sigungu_code
    )

    # 전체 인구는 계_로 시작하는 열만 사용
    total_columns = [
        c for c in df.columns
        if c.startswith("계_")
    ]

    if not total_columns:
        raise ValueError(
            "'계_'로 시작하는 인구 열을 찾지 못했습니다."
        )

    # 65세 이상 인구 열
    aging_columns = [
        c for c in total_columns
        if (
            get_age_number(c) is not None
            and get_age_number(c) >= 65
        )
    ]

    # 0~14세 유소년 인구 열
    youth_columns = [
        c for c in total_columns
        if (
            get_age_number(c) is not None
            and 0 <= get_age_number(c) <= 14
        )
    ]

    if not aging_columns:
        raise ValueError(
            "65세 이상 인구 열을 찾을 수 없습니다."
        )

    if not youth_columns:
        raise ValueError(
            "0~14세 인구 열을 찾을 수 없습니다."
        )

    # 인구 열을 숫자로 변환
    df[total_columns] = (
        df[total_columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    # 동별 인구 계산
    df["전체인구"] = df[total_columns].sum(axis=1)
    df["65세이상인구"] = df[aging_columns].sum(axis=1)
    df["유소년인구"] = df[youth_columns].sum(axis=1)

    # 수정된 부분:
    # 한글 변수를 named aggregation에 직접 쓰지 않고
    # 일반 딕셔너리 방식으로 집계한다.
    grouped = (
        df.groupby(
            ["연도", "시군구코드"],
            as_index=False
        )
        .agg({
            "전체인구": "sum",
            "65세이상인구": "sum",
            "유소년인구": "sum"
        })
    )

    # 인구 합계로 비율 계산
    grouped["고령화율"] = (
        grouped["65세이상인구"]
        .div(
            grouped["전체인구"].where(
                grouped["전체인구"] > 0
            )
        )
        * 100
    )

    grouped["유소년비율"] = (
        grouped["유소년인구"]
        .div(
            grouped["전체인구"].where(
                grouped["전체인구"] > 0
            )
        )
        * 100
    )

    return grouped


# ==========================================
# 4. GeoJSON 경계 불러오기
# ==========================================
@st.cache_data(ttl=3600)
def load_geojson():
    response = requests.get(
        GEOJSON_URL,
        timeout=120
    )
    response.raise_for_status()

    geojson = response.json()

    if "features" not in geojson:
        raise ValueError(
            "GeoJSON에 features가 없습니다."
        )

    for feature in geojson["features"]:
        properties = feature.setdefault(
            "properties", {}
        )

        if "코드" not in properties:
            raise ValueError(
                "GeoJSON에 '코드' 속성이 없습니다."
            )

        code = correct_sigungu_code(
            properties["코드"]
        )

        properties["코드"] = code
        feature["id"] = code

    return geojson


# ==========================================
# 5. 데이터 로드
# ==========================================
try:
    population = load_population()
    geojson = load_geojson()

except Exception as error:
    st.error("데이터를 불러오는 중 오류가 발생했습니다.")
    st.exception(error)
    st.stop()


# ==========================================
# 6. 지도 경계 데이터 구성
# ==========================================
boundary_rows = []

for feature in geojson["features"]:
    properties = feature["properties"]

    boundary_rows.append({
        "코드": str(feature["id"]),
        "시군구": str(properties.get("시군구", "")),
        "시도": str(properties.get("시도", ""))
    })

boundaries = pd.DataFrame(boundary_rows)

# 동일한 코드가 중복되는 경우 한 개만 유지
boundaries = boundaries.drop_duplicates(
    subset=["코드"]
)

sido_options = sorted(
    boundaries["시도"].dropna().unique().tolist()
)

available_years = sorted(
    population["연도"].unique().tolist()
)

if not available_years:
    st.error("선택할 수 있는 연도가 없습니다.")
    st.stop()


# ==========================================
# 7. 사용자 선택 영역
# ==========================================
control1, control2, control3 = st.columns(
    [1.2, 1.5, 2]
)

with control1:
    selected_year = st.select_slider(
        "기준 연도",
        options=available_years,
        value=max(available_years),
        format_func=lambda y: f"{y}년"
    )

with control2:
    selected_sido = st.selectbox(
        "표시할 시도",
        options=["전국"] + sido_options,
        index=0
    )

with control3:
    selected_indicator = st.selectbox(
        "지도 지표",
        options=[
            "고령화율 (65세 이상)",
            "유소년 비율 (0~14세)"
        ]
    )


# ==========================================
# 8. 연도별 데이터 결합
# ==========================================
year_population = population[
    population["연도"] == selected_year
].copy()

map_df = boundaries.merge(
    year_population,
    left_on="코드",
    right_on="시군구코드",
    how="left",
    validate="one_to_one"
)

# 시도 선택에 따른 지도 필터링
if selected_sido != "전국":
    map_df = map_df[
        map_df["시도"] == selected_sido
    ].copy()

visible_codes = set(
    map_df["코드"].astype(str)
)

visible_geojson = {
    "type": "FeatureCollection",
    "features": [
        feature
        for feature in geojson["features"]
        if str(feature["id"]) in visible_codes
    ]
}


# ==========================================
# 9. 지표별 색상 구간 설정
# ==========================================
if selected_indicator == "고령화율 (65세 이상)":
    value_column = "고령화율"
    numerator_column = "65세이상인구"
    bins = AGING_BINS
    labels = AGING_LABELS
    color_map = AGING_COLORS
    map_title = f"{selected_year}년 시군구별 고령화율"

else:
    value_column = "유소년비율"
    numerator_column = "유소년인구"
    bins = YOUTH_BINS
    labels = YOUTH_LABELS
    color_map = YOUTH_COLORS
    map_title = f"{selected_year}년 시군구별 유소년 비율"

# 자료가 없는 지역은 '자료 없음' 단계로 분류
map_df["단계"] = pd.cut(
    map_df[value_column],
    bins=bins,
    labels=labels,
    right=False
).astype("object")

map_df.loc[
    map_df[value_column].isna(),
    "단계"
] = "자료 없음"

category_order = labels + ["자료 없음"]


# ==========================================
# 10. 지표 카드 3개
# ==========================================
valid_df = map_df.dropna(
    subset=[value_column]
).copy()

if not valid_df.empty:
    total_population = valid_df["전체인구"].sum()
    numerator_population = valid_df[
        numerator_column
    ].sum()

    overall_rate = (
        numerator_population / total_population * 100
        if total_population > 0
        else None
    )

    highest_row = valid_df.loc[
        valid_df[value_column].idxmax()
    ]

    lowest_row = valid_df.loc[
        valid_df[value_column].idxmin()
    ]

else:
    overall_rate = None
    highest_row = None
    lowest_row = None


if selected_indicator == "고령화율 (65세 이상)":
    rate_label = "고령화율"
else:
    rate_label = "유소년 비율"

if selected_sido == "전국":
    first_card_title = f"전국 {rate_label}"
else:
    first_card_title = f"{selected_sido} {rate_label}"

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        first_card_title,
        (
            f"{overall_rate:.2f}%"
            if overall_rate is not None
            else "자료 없음"
        )
    )

with card2:
    if highest_row is not None:
        st.metric(
            "비율이 가장 높은 시군구",
            highest_row["시군구"],
            f'{highest_row[value_column]:.2f}%'
        )
    else:
        st.metric(
            "비율이 가장 높은 시군구",
            "자료 없음"
        )

with card3:
    if lowest_row is not None:
        st.metric(
            "비율이 가장 낮은 시군구",
            lowest_row["시군구"],
            f'{lowest_row[value_column]:.2f}%'
        )
    else:
        st.metric(
            "비율이 가장 낮은 시군구",
            "자료 없음"
        )


# ==========================================
# 11. 단계구분도 생성
# ==========================================
st.subheader(map_title)

if map_df.empty or not visible_geojson["features"]:
    st.warning("선택한 지역의 지도 경계가 없습니다.")

else:
    fig = px.choropleth(
        map_df,
        geojson=visible_geojson,
        locations="코드",
        featureidkey="id",
        color="단계",
        category_orders={
            "단계": category_order
        },
        color_discrete_map=color_map,
        hover_name="시군구",
        custom_data=[value_column],
        labels={
            "단계": "비율 구간"
        }
    )

    # 배경 타일 없이 경계만 표시
    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=False,
        showcoastlines=False,
        showland=False,
        showframe=False,
        bgcolor="rgba(0,0,0,0)"
    )

    hover_label = (
        "고령화율"
        if selected_indicator == "고령화율 (65세 이상)"
        else "유소년 비율"
    )

    fig.update_traces(
        marker_line_color="white",
        marker_line_width=0.45,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            + hover_label
            + ": %{customdata[0]:.2f}%"
            + "<extra></extra>"
        )
    )

    fig.update_layout(
        height=760,
        margin=dict(
            l=0,
            r=0,
            t=20,
            b=20
        ),
        legend_title_text="비율 구간",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.04,
            xanchor="center",
            x=0.5
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "scrollZoom": True,
            "displayModeBar": True
        }
    )


# ==========================================
# 12. 코드 불일치 및 자료 누락 안내
# ==========================================
missing_df = map_df[
    map_df[value_column].isna()
].copy()

if not missing_df.empty:
    st.warning(
        f"선택한 지역 중 {len(missing_df)}개 시군구는 "
        "해당 연도 인구 자료가 없거나 경계 코드와 일치하지 않아 "
        "회색으로 표시됩니다. 행정구역 개편이나 자료 누락 여부를 "
        "확인하세요."
    )


# ==========================================
# 13. 시군구별 상세 표
# ==========================================
with st.expander("시군구별 인구 및 코드 확인"):
    display_columns = [
        "시도",
        "시군구",
        "코드",
        "전체인구",
        "65세이상인구",
        "고령화율",
        "유소년인구",
        "유소년비율"
    ]

    available_columns = [
        column
        for column in display_columns
        if column in map_df.columns
    ]

    table = map_df[
        available_columns
    ].copy()

    for column in [
        "고령화율",
        "유소년비율"
    ]:
        if column in table.columns:
            table[column] = table[column].round(2)

    table = table.sort_values(
        by=value_column,
        ascending=False,
        na_position="last"
    )

    st.dataframe(
        table,
        width="stretch",
        hide_index=True
    )
