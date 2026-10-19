
import json
import re
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------
# 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="",
    layout="wide"
)

st.title("전국 고령화 단계구분도")
st.caption("2026년 6월 기준 · 시군구별 65세 이상 인구 비율")

POPULATION_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)

# -----------------------------
# 데이터 불러오기
# -----------------------------
@st.cache_data(ttl=3600, show_spinner="인구 데이터를 불러오는 중...")
def load_population():
    response = requests.get(POPULATION_URL, timeout=120)
    response.raise_for_status()

    # pandas는 ZIP 안의 CSV를 직접 읽을 수 있음
    from io import BytesIO
    df = pd.read_csv(BytesIO(response.content), compression="zip",
                     dtype={"코드": "string"})

    required = ["연도", "코드"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"인구 데이터에 필요한 열이 없습니다: {missing}")

    # 연도 열을 숫자로 통일한 뒤 2026년만 선택
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df[df["연도"] == 2026].copy()

    if df.empty:
        raise ValueError("인구 데이터에서 2026년 자료를 찾지 못했습니다.")

    # 코드는 문자열로 처리하고 앞 5자리를 시군구 코드로 사용
    df["코드"] = (
        df["코드"].astype("string").str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
    )
    df["시군구코드"] = df["코드"].str[:5]

    # 계_로 시작하는 열만 집계. 남_·여_ 열은 제외
    total_cols = [
        c for c in df.columns
        if c.startswith("계_")
    ]

    # 65세 이상 열: 계_65세부터 계_100세 이상까지
    elderly_cols = []
    for c in total_cols:
        age = c.removeprefix("계_").strip()
        match = re.fullmatch(r"(\d+)세", age)
        if (match and int(match.group(1)) >= 65) or age == "100세 이상":
            elderly_cols.append(c)

    if not total_cols:
        raise ValueError("'계_'로 시작하는 인구 열을 찾지 못했습니다.")
    if not elderly_cols:
        raise ValueError("65세 이상 인구 열을 찾지 못했습니다.")

    # 숫자로 변환하고 결측치는 0으로 처리
    df[total_cols] = df[total_cols].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0)
    df[elderly_cols] = df[elderly_cols].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0)

    df["전체인구"] = df[total_cols].sum(axis=1)
    df["65세이상인구"] = df[elderly_cols].sum(axis=1)

    # 동별 인구를 시군구 코드 기준으로 합산
    grouped = (
        df.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            **{"65세이상인구": ("65세이상인구", "sum")}
        )
    )

    grouped["고령화율"] = (
        grouped["65세이상인구"]
        .div(grouped["전체인구"].where(grouped["전체인구"] != 0))
        .mul(100)
    )

    return grouped


@st.cache_data(ttl=3600, show_spinner="시군구 경계를 불러오는 중...")
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=120)
    response.raise_for_status()
    geo = response.json()

    # GeoJSON 속성 코드와 지도 Feature ID를 문자열로 통일
    for feature in geo.get("features", []):
        props = feature.setdefault("properties", {})
        code = str(props.get("코드", "")).strip()

        if code.endswith(".0"):
            code = code[:-2]

        code = code.zfill(5)
        props["코드"] = code
        feature["id"] = code

    return geo


# -----------------------------
# 데이터 처리 및 지도 생성
# -----------------------------
try:
    population = load_population()
    geojson = load_geojson()

    # GeoJSON 속성에서 코드와 이름을 가져옴
    boundaries = pd.DataFrame([
        {
            "코드": feature["id"],
            "시군구": feature["properties"].get("시군구", ""),
            "시도": feature["properties"].get("시도", "")
        }
        for feature in geojson["features"]
    ])

    # 이름이 아닌 코드로만 결합
    map_df = boundaries.merge(
        population,
        left_on="코드",
        right_on="시군구코드",
        how="left",
        validate="one_to_one"
    )

    matched = map_df["고령화율"].notna().sum()
    unmatched = len(map_df) - matched

    if matched == 0:
        st.error(
            "지도 경계 코드와 인구 데이터 코드가 하나도 일치하지 않습니다. "
            "두 파일의 코드 형식과 데이터 연도를 확인하세요."
        )
        st.stop()

    # 데이터가 없는 지역은 회색으로 표시
    map_df["지도값"] = map_df["고령화율"]

    fig = px.choropleth(
        map_df,
        geojson=geojson,
        locations="코드",
        featureidkey="id",
        color="지도값",
        color_continuous_scale="YlOrRd",
        range_color=(0, 100),
        hover_name="시군구",
        hover_data={
            "코드": False,
            "지도값": False,
            "고령화율": ":.2f",
            "전체인구": ":,.0f",
            "65세이상인구": ":,.0f"
        },
        labels={
            "고령화율": "65세 이상 비율(%)",
            "전체인구": "전체 인구(명)",
            "65세이상인구": "65세 이상 인구(명)",
            "지도값": "고령화율(%)"
        },
        title="시군구별 65세 이상 인구 비율"
    )

    # 배경 타일 없이 경계선만 표시
    fig.update_geos(
        fitbounds="locations",
        visible=False,
        showcountries=False,
        showcoastlines=False,
        showland=False,
        showframe=False,
        bgcolor="rgba(0,0,0,0)"
    )

    fig.update_traces(
        marker_line_color="white",
        marker_line_width=0.45,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "고령화율: %{z:.2f}%<extra></extra>"
        )
    )

    # hover_name이 시군구 이름을 표시하도록 하고
    # hovertemplate에는 시군구명과 고령화율을 명시
    fig.update_traces(
        customdata=map_df[["시군구"]].to_numpy(),
        z=map_df["고령화율"],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "고령화율: %{z:.2f}%<extra></extra>"
        )
    )

    fig.update_layout(
        height=780,
        margin=dict(l=0, r=0, t=65, b=0),
        coloraxis_colorbar=dict(
            title="고령화율(%)",
            ticksuffix="%",
            thickness=16,
            len=0.72
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

    # -----------------------------
    # 요약 정보
    # -----------------------------
    c1, c2, c3 = st.columns(3)
    c1.metric("지도에 표시된 시군구", f"{matched:,}개")
    c2.metric("경계는 있으나 인구 자료가 없는 지역", f"{unmatched:,}개")

    if matched:
        valid = map_df.dropna(subset=["고령화율"])
        highest = valid.loc[valid["고령화율"].idxmax()]
        c3.metric(
            "고령화율이 가장 높은 시군구",
            str(highest["시군구"]),
            f'{highest["고령화율"]:.2f}%'
        )

    with st.expander("시군구별 고령화율 표 보기"):
        table = map_df.loc[
            map_df["고령화율"].notna(),
            ["시도", "시군구", "코드", "전체인구", "65세이상인구", "고령화율"]
        ].copy()
        table["고령화율"] = table["고령화율"].round(2)
        table = table.sort_values("고령화율", ascending=False)
        st.dataframe(table, width="stretch", hide_index=True)

    if unmatched:
        st.warning(
            f"경계 코드와 인구 코드가 일치하지 않는 지역이 {unmatched}개 있습니다. "
            "해당 지역은 지도에서 색상 값이 표시되지 않을 수 있습니다."
        )

except Exception as e:
    st.error("데이터를 불러오거나 지도를 만드는 중 오류가 발생했습니다.")
    st.exception(e)
