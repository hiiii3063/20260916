
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# -----------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------
st.set_page_config(
    page_title="동네별 인구 피라미드",
    page_icon="📊",
    layout="wide"
)

# 따뜻한 색상의 화면 디자인
st.markdown("""
<style>
.stApp {
    background-color: #FFF8F0;
}
h1, h2, h3 {
    color: #76513D;
}
div[data-testid="stMetric"] {
    background-color: #FFFFFF;
    border: 1px solid #E8D6C5;
    border-radius: 12px;
    padding: 12px;
}
</style>
""", unsafe_allow_html=True)

st.title("동네별 인구 피라미드")
st.write("지역을 선택해 연령별 남녀 인구를 비교해 보세요.")

# -----------------------------------------------
# 2. 데이터 불러오기
# ZIP 압축 파일도 pandas가 직접 읽을 수 있습니다.
# -----------------------------------------------
DATA_URL = (
    "https://raw.githubusercontent.com/"
    "first2022-cyber/contents/main/"
    "population_ts_yearly_gender.zip"
)

@st.cache_data
def load_data():
    # 원격 ZIP 파일을 읽고 열 이름의 공백을 제거합니다.
    data = pd.read_csv(DATA_URL, compression="zip")
    data.columns = data.columns.astype(str).str.strip()
    return data

try:
    df = load_data()
except Exception as e:
    st.error("인구 데이터를 불러오지 못했습니다.")
    st.write("인터넷 연결과 CSV 주소를 확인해 주세요.")
    st.exception(e)
    st.stop()

# -----------------------------------------------
# 3. 최신 연도 데이터만 선택
# -----------------------------------------------
required_columns = ["연도", "시도", "시군구", "동"]
missing_columns = [
    col for col in required_columns if col not in df.columns
]

if missing_columns:
    st.error(f"필수 열이 없습니다: {missing_columns}")
    st.stop()

df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
df = df.dropna(subset=["연도"]).copy()

if df.empty:
    st.error("유효한 연도 데이터가 없습니다.")
    st.stop()

# 데이터에 실제로 존재하는 가장 최신 연도를 찾습니다.
latest_year = int(df["연도"].max())
df = df[df["연도"] == latest_year].copy()

# 지역명은 문자열로 통일하고 앞뒤 공백을 제거합니다.
for col in ["시도", "시군구", "동"]:
    df[col] = df[col].fillna("").astype(str).str.strip()

df = df[
    (df["시도"] != "") &
    (df["시군구"] != "") &
    (df["동"] != "")
].copy()

# -----------------------------------------------
# 4. 연령별 인구 열 준비
# 0세부터 99세, 마지막으로 100세 이상을 표시합니다.
# -----------------------------------------------
age_labels = [f"{age}세" for age in range(100)]
age_labels.append("100세 이상")

male_columns = [f"남_{age}" for age in age_labels]
female_columns = [f"여_{age}" for age in age_labels]

needed_columns = male_columns + female_columns
missing_age_columns = [
    col for col in needed_columns if col not in df.columns
]

if missing_age_columns:
    st.error("일부 연령별 인구 열을 찾을 수 없습니다.")
    st.write("누락된 열 예시:", missing_age_columns[:10])
    st.stop()

# 숫자 열을 숫자형으로 바꾸고 결측값은 0으로 처리합니다.
for col in needed_columns:
    df[col] = pd.to_numeric(
        df[col].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    ).fillna(0)

# -----------------------------------------------
# 5. 시도 → 시군구 → 동 선택
# -----------------------------------------------
st.subheader("지역 선택")

col1, col2, col3 = st.columns(3)

with col1:
    sido_options = sorted(df["시도"].unique().tolist())
    selected_sido = st.selectbox("시도", sido_options)

sido_df = df[df["시도"] == selected_sido]

with col2:
    sigungu_options = sorted(sido_df["시군구"].unique().tolist())
    selected_sigungu = st.selectbox("시군구", sigungu_options)

sigungu_df = sido_df[sido_df["시군구"] == selected_sigungu]

with col3:
    dong_options = sorted(sigungu_df["동"].unique().tolist())
    selected_dong = st.selectbox("동", dong_options)

# -----------------------------------------------
# 6. 선택한 동네의 연령별 인구 계산
# 같은 지역의 행이 여러 개라면 연령별로 합산합니다.
# -----------------------------------------------
selected_df = sigungu_df[
    sigungu_df["동"] == selected_dong
]

if selected_df.empty:
    st.warning("선택한 지역의 데이터가 없습니다.")
    st.stop()

male_population = (
    selected_df[male_columns].sum(axis=0).to_numpy(dtype=float)
).clip(min=0)

female_population = (
    selected_df[female_columns].sum(axis=0).to_numpy(dtype=float)
).clip(min=0)

male_total = int(male_population.sum())
female_total = int(female_population.sum())
total_population = male_total + female_total

st.divider()
st.subheader(
    f"{selected_sido} {selected_sigungu} {selected_dong}"
)
st.caption(f"기준 연도: {latest_year}년")

metric1, metric2, metric3 = st.columns(3)
metric1.metric("총인구", f"{total_population:,}명")
metric2.metric("남성 인구", f"{male_total:,}명")
metric3.metric("여성 인구", f"{female_total:,}명")

# -----------------------------------------------
# 7. 인구 피라미드 그래프
# 남성은 음수로 변환해 왼쪽에, 여성은 양수로 오른쪽에 표시합니다.
# -----------------------------------------------
fig = go.Figure()

fig.add_trace(go.Bar(
    x=-male_population,
    y=age_labels,
    orientation="h",
    name="남성",
    marker_color="#789BC2",
    customdata=male_population,
    hovertemplate=(
        "나이: %{y}<br>"
        "남성 인구: %{customdata:,.0f}명"
        "<extra></extra>"
    )
))

fig.add_trace(go.Bar(
    x=female_population,
    y=age_labels,
    orientation="h",
    name="여성",
    marker_color="#D98F96",
    customdata=female_population,
    hovertemplate=(
        "나이: %{y}<br>"
        "여성 인구: %{customdata:,.0f}명"
        "<extra></extra>"
    )
))

# 양쪽 인구 막대가 대칭으로 보이도록 가로축 범위를 설정합니다.
max_population = max(
    float(male_population.max()),
    float(female_population.max()),
    1.0
)
axis_limit = max_population * 1.1

# 핵심: 나이 라벨을 0세부터 100세 이상까지 직접 고정합니다.
# Plotly의 카테고리 축은 기본적으로 첫 번째 항목이 아래에
# 놓일 수 있으므로 categoryorder와 categoryarray를 명시합니다.
fig.update_layout(
    title={
        "text": "연령별 남녀 인구 피라미드",
        "x": 0.5,
        "xanchor": "center"
    },
    barmode="overlay",
    bargap=0.12,
    height=1100,
    paper_bgcolor="#FFF8F0",
    plot_bgcolor="#FFFCF8",
    font=dict(
        family="Arial, sans-serif",
        size=12,
        color="#594638"
    ),
    margin=dict(l=100, r=35, t=90, b=70),
    legend=dict(
        title="성별",
        orientation="h",
        x=0.5,
        xanchor="center",
        y=1.02,
        yanchor="bottom"
    ),
    xaxis=dict(
        title="인구 수 (명)",
        range=[-axis_limit, axis_limit],
        tickformat=",.0f",
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="#9B8573",
        gridcolor="#EDE2D8"
    ),
    yaxis=dict(
        title="나이",
        type="category",
        categoryorder="array",
        categoryarray=age_labels,
        tickmode="array",
        tickvals=age_labels,
        ticktext=age_labels,
        showgrid=True,
        gridcolor="#F0E7DE"
    )
)

st.plotly_chart(fig, use_container_width=True)

st.caption(
    "가운데 0을 기준으로 왼쪽은 남성, 오른쪽은 여성입니다. "
    "나이는 아래에서 위로 증가하며, 맨 아래는 0세, "
    "맨 위는 100세 이상입니다."
)

# -----------------------------------------------
# 8. 연령별 상세 표
# -----------------------------------------------
with st.expander("연령별 인구 상세 표"):
    detail_df = pd.DataFrame({
        "나이": age_labels,
        "남성 인구": male_population.astype(int),
        "여성 인구": female_population.astype(int),
        "전체 인구": (
            male_population + female_population
        ).astype(int)
    })

    st.dataframe(
        detail_df,
        use_container_width=True,
        hide_index=True
    )

st.caption("자료: 지정된 GitHub 인구 데이터 파일")
