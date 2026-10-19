
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
    page_title="전국 고령화 단계구분도",
    page_icon="",
    layout="wide"
)

st.title("전국 인구 구조 단계구분도")
st.caption("2015~2026년 6월 기준 · 시군구별 인구 비율 지도")

POPULATION_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)

# 고령화율은 모든 연도에서 같은 구간 사용
AGING_BINS = [0, 19, 23, 28, 38, 100]
AGING_LABELS = [
    "19% 미만",
    "19~23% 미만",
    "23~28% 미만",
    "28~38% 미만",
    "38% 이상"
]

# 유소년 비율은 별도의 고정 구간 사용
# 연도별 비교를 위해 이 구간도 연도에 따라 바꾸지 않음
YOUTH_BINS = [0, 6, 9, 12, 15, 100]
YOUTH_LABELS = [
    "6% 미만",
    "6~9% 미만",
    "9~12% 미만",
    "12~15% 미만",
    "15% 이상"
]

# 낮은 비율부터 높은 비율 순서
COLOR_MAP = {
    "19% 미만": "#fff5eb",
    "19~23% 미만": "#fdd49e",
    "23~28% 미만": "#fdbb84",
    "28~38% 미만": "#e34a33",
    "38% 이상": "#990000",

    "6% 미만": "#f7fbff",
    "6~9% 미만": "#c6dbef",
    "9~12% 미만": "#6baed6",
    "12~15% 미만": "#2171b5",
    "15% 이상": "#08306b",

    "자료 없음": "#d3d3d3"
}


# ==========================================
# 2. 코드 정리 함수
# ==========================================
def normalize_code(value):
    """행정구역 코드를 문자열로 정리한다."""
    if pd.isna(value):
        return ""

    code = str(value).strip()

    # 숫자형 CSV에서 생긴 12345.0 형태 처리
    if code.endswith(".0"):
        code = code[:-2]

    # 공백 제거 및 숫자 코드 정리
    code = re.sub(r"\s+", "", code)

    if not code:
        return ""

    # 시군구 5자리 코드
    if len(code) <= 5:
        code = code.zfill(5)
    else:
        code = code.zfill(10)

    return code


def correct_sigungu_code(code):
    """
    과거 행정구역 코드를 현재 경계 코드에 맞게 변환한다.
    강원: 42 -> 51
    전북: 45 -> 52
    군위군: 47720 -> 27720
    """
    code = normalize_code(code)

    if not code:
        return ""

    # 시군구 코드 5자리만 변환
    sigungu_code = code[:5]

    if sigungu_code == "47720":
        sigungu_code = "27720"
    elif sigungu_code.startswith("42"):
        sigungu_code = "51" + sigungu_code[2:]
    elif sigungu_code.startswith("45"):
        sigungu_code = "52" + sigungu_code[2:]

    return sigungu_code


def get_age_number(column):
    """계_65세 같은 열에서 나이를 추출한다."""
    age_text = column.removeprefix("계_").strip()

    if age_text == "100세 이상":
        return 100

    match = re.fullmatch(r"(\d+)세", age_text)
    if match:
        return int(match.group(1))

    return None


# ==========================================
# 3. 인구 데이터 불러오기
# ==========================================
@st.cache_data(ttl=3600, show_spinner="인구 데이터를 불러오는 중...")
def load_population():
    response = requests.get(POPULATION_URL, timeout=120)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        dtype={"코드": "string"}
    )

    required_columns = ["연도", "코드"]
    missing = [
        column for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"인구 데이터에 필요한 열이 없습니다: {missing}"
        )

    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df.dropna(subset=["연도", "코드"]).copy()
    df["연도"] = df["연도"].astype(int)

    # 행정구역 코드는 문자열로 유지
    df["코드"] = df["코드"].map(normalize_code)
    df["시군구코드"] = df["코드"].map(correct_sigungu_code)

    # 전체 인구: 계_로 시작하는 열만 사용
    total_columns = [
        column for column in df.columns
        if column.startswith("계_")
    ]

    if not total_columns:
        raise ValueError("'계_'로 시작하는 인구 열이 없습니다.")

    # 65세 이상: 계_65세 ~ 계_100세 이상
    aging_columns = [
        column for column in total_columns
        if (
            get_age_number(column) is not None
            and get_age_number(column) >= 65
        )
    ]

    # 유소년: 계_0세 ~ 계_14세
    youth_columns = [
        column for column in total_columns
        if (
            get_age_number(column) is not None
            and 0 <= get_age_number(column) <= 14
        )
    ]

    if not aging_columns:
        raise ValueError("65세 이상 인구 열을 찾지 못했습니다.")

    if not youth_columns:
        raise ValueError("0~14세 인구 열을 찾지 못했습니다.")

    # 인구 열의 결측치 및 숫자형 변환
    df[total_columns] = (
        df[total_columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    df["전체인구"] = df[total_columns].sum(axis=1)
    df["65세이상인구"] = df[aging_columns].sum(axis=1)
    df["유소년인구"] = df[youth_columns].sum(axis=1)

    # 연도와 시군구 코드별로 합산
    grouped = (
        df.groupby(
            ["연도", "시군구코드"],
            as_index=False
        )
        .agg(
            전체인구=("전체인구", "sum"),
            65세이상인구=("65세이상인구", "sum"),
            유소년인구=("유소년인구", "sum")
        )
    )

    grouped["고령화율"] = (
        grouped["65세이상인구"]
        .div(grouped["전체인구"].where(grouped["전체인구"] > 0))
        * 100
    )

    grouped["유소년비율"] = (
        grouped["유소년인구"]
        .div(grouped["전체인구"].where(grouped["전체인구"] > 0))
        * 100
    )

    return grouped


# ==========================================
# 4. GeoJSON 불러오기
# ==========================================
@st.cache_data(ttl=3600, show_spinner="시군구 경계를 불러오는 중...")
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=120)
    response.raise_for_status()

    geojson = response.json()

    if "features" not in geojson:
        raise ValueError("GeoJSON에 features가 없습니다.")

    for feature in geojson["features"]:
        properties = feature.setdefault("properties", {})

        if "코드" not in properties:
            raise ValueError(
                "GeoJSON에서 '코드' 속성을 찾지 못했습니다."
            )

        code = normalize_code(properties["코드"])

        # 경계 코드에도 동일한 코드 보정 적용
        code = correct_sigungu_code(code)

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
    st.error("데이터를 불러오지 못했습니다.")
    st.exception(error)
    st.stop()


# ==========================================
# 6. 지도 경계 데이터 준비
# ==========================================
boundary_rows = []

for feature in geojson["features"]:
    properties = feature["properties"]

    boundary_rows.append({
        "코드": feature["id"],
        "시군구": str(properties.get("시군구", "")),
        "시도": str(properties.get("시도", ""))
    })

boundaries = pd.DataFrame(boundary_rows)

boundaries = boundaries.drop_duplicates(subset=["코드"])

# 시도 선택 목록
sido_options = sorted(
    boundaries["시도"].dropna().unique().tolist()
)

# 연도 선택 목록
available_years = sorted(
    population["연도"].dropna().unique().tolist()
)

if not available_years:
    st.error("인구 데이터에서 연도를 찾지 못했습니다.")
    st.stop()


# ==========================================
# 7. 선택 컨트롤
# ==========================================
control1, control2, control3 = st.columns([1.4, 1.5, 2])

with control1:
    selected_year = st.select_slider(
        "기준 연도",
        options=available_years,
        value=max(available_years),
        format_func=lambda year: f"{year}년"
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
        options=["고령화율 (65세 이상)", "유소년 비율 (0~14세)"],
        index=0
    )


# ==========================================
# 8. 연도별 인구 데이터 및 지도 데이터 결합
# ==========================================
year_population = population[
    population["연도"] == selected_year
].copy()

# 코드로만 결합
map_df = boundaries.merge(
    year_population,
    left_on="코드",
    right_on="시군구코드",
    how="left",
    validate="one_to_one"
)

# 전국 또는 선택한 시도만 표시
if selected_sido != "전국":
    map_df = map_df[
        map_df["시도"] == selected_sido
    ].copy()

# 지도 범위에 맞는 GeoJSON feature만 남김
visible_codes = set(map_df["코드"].astype(str))

visible_geojson = {
    "type": "FeatureCollection",
    "features": [
        feature
        for feature in geojson["features"]
        if feature["id"] in visible_codes
    ]
}

# 선택한 지표에 따라 값과 구간 설정
if selected_indicator == "고령화율 (65세 이상)":
    value_column = "고령화율"
    bins = AGING_BINS
    labels = AGING_LABELS
    map_title = f"{selected_year}년 시군구별 고령화율"
    color_title = "고령화율"
    colors = {
        label: COLOR_MAP[label]
        for label in AGING_LABELS
    }
else:
    value_column = "유소년비율"
    bins = YOUTH_BINS
    labels = YOUTH_LABELS
    map_title = f"{selected_year}년 시군구별 유소년 비율"
    color_title = "유소년 비율"
    colors = {
        label: COLOR_MAP[label]
        for label in YOUTH_LABELS
    }

# 자료가 없는 지역은 지도에서 회색으로 표시
map_df["단계"] = pd.cut(
    map_df[value_column],
    bins=bins,
    labels=labels,
    right=False,
    include_lowest=True
).astype("object")

map_df["단계"] = map_df["단계"].where(
    map_df[value_column].notna(),
    "자료 없음"
)

# 색상 범례 순서 고정
category_order = labels + ["자료 없음"]
colors["자료 없음"] = COLOR_MAP["자료 없음"]


# ==========================================
# 9. 지표 카드
# ==========================================
valid_df = map_df.dropna(subset=[value_column]).copy()

if selected_indicator == "고령화율 (65세 이상)":
    numerator_column = "65세이상인구"
else:
    numerator_column = "유소년인구"

# 전국 고령화율은 전국 인구를 합산해 계산
# 시도를 선택한 경우 해당 시도의 합산 비율 계산
if not valid_df.empty:
    total_population = valid_df["전체인구"].sum()
    numerator_population = valid_df[numerator_column].sum()

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

metric1, metric2, metric3 = st.columns(3)

rate_name = (
    "전국 고령화율"
    if selected_indicator == "고령화율 (65세 이상)"
    else "전국 유소년 비율"
)

if selected_sido != "전국":
    rate_name = (
        f"{selected_sido} 고령화율"
        if selected_indicator == "고령화율 (65세 이상)"
        else f"{selected_sido} 유소년 비율"
    )

with metric1:
    st.metric(
        rate_name,
        f"{overall_rate:.2f}%" if overall_rate is not None else "자료 없음"
    )

with metric2:
    if highest_row is not None:
        st.metric(
            "비율이 가장 높은 시군구",
            highest_row["시군구"],
            f'{highest_row[value_column]:.2f}%'
        )
    else:
        st.metric("비율이 가장 높은 시군구", "자료 없음")

with metric3:
    if lowest_row is not None:
        st.metric(
            "비율이 가장 낮은 시군구",
            lowest_row["시군구"],
            f'{lowest_row[value_column]:.2f}%'
        )
    else:
        st.metric("비율이 가장 낮은 시군구", "자료 없음")


# ==========================================
# 10. 단계구분도 생성
# ==========================================
st.subheader(map_title)

if map_df.empty or not visible_geojson["features"]:
    st.warning("선택한 지역의 경계 자료가 없습니다.")
else:
    fig = px.choropleth(
        map_df,
        geojson=visible_geojson,
        locations="코드",
        featureidkey="id",
        color="단계",
        category_orders={"단계": category_order},
        color_discrete_map=colors,
        hover_name="시군구",
        hover_data={
            "코드": False,
            "단계": False,
            value_column: ":.2f",
            "전체인구": ":,.0f"
        },
        labels={
            value_column: (
                "고령화율(%)"
                if selected_indicator == "고령화율 (65세 이상)"
                else "유소년 비율(%)"
            ),
            "전체인구": "전체 인구(명)",
            "시군구": "시군구"
        }
    )

    # 배경 타일 없이 행정구역 경계만 표시
    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=False,
        showcoastlines=False,
        showland=False,
        showframe=False,
        bgcolor="rgba(0,0,0,0)"
    )

    # hover에는 지역명과 선택한 비율만 표시
    fig.update_traces(
        marker_line_color="white",
        marker_line_width=0.45,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            + (
                "고령화율: %{customdata[0]:.2f}%"
                if selected_indicator == "고령화율 (65세 이상)"
                else "유소년 비율: %{customdata[0]:.2f}%"
            )
            + "<extra></extra>"
        ),
        customdata=map_df[[value_column]].to_numpy()
    )

    fig.update_layout(
        height=760,
        margin=dict(l=0, r=0, t=20, b=0),
        legend_title_text=color_title,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.02,
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
# 11. 자료 불일치 안내
# ==========================================
unmatched_df = map_df[
    map_df["고령화율"].isna()
].copy()

if not unmatched_df.empty:
    st.warning(
        f"선택한 지역 중 {len(unmatched_df)}개 시군구는 "
        "해당 연도 인구 자료와 경계 코드가 일치하지 않거나 "
        "인구 자료가 없어 회색으로 표시됩니다. "
        "행정구역 개편, 코드 변경 또는 자료 누락 여부를 확인하세요."
    )

# 선택 지역 내 코드별 매칭 결과 확인
with st.expander("시군구별 수치 및 코드 확인"):
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
        column for column in display_columns
        if column in map_df.columns
    ]

    table = map_df[available_columns].copy()

    for column in ["고령화율", "유소년비율"]:
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
