
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

# 따뜻한 색상 테마
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
    padding: 14px;
}
div[data-testid="stMetricLabel"] {
    color: #76513D;
}
</style>
""", unsafe_allow_html=True)

st.title("동네별 인구 피라미드")
st.write("지역을 선택해 연령별 남녀 인구를 비교해 보세요.")

# -----------------------------------------------
# 2. 데이터 불러오기
# -----------------------------------------------
DATA_URL = (
    "https://raw.githubusercontent.com/"
    "first2022-cyber/contents/main/"
    "population_ts_yearly_gender.zip"
)

@st.cache_data
def load_data():
    # ZIP 압축 파일을 직접 읽습니다.
    data = pd.read_csv(
        DATA_URL,
        compression="zip",
        encoding="utf-8-sig"
    )
    data.columns = data.columns.astype(str).str.strip()
    return data

try:
    df = load_data()
except Exception as e:
    st.error("인구 데이터를 불러오지 못했습니다.")
    st.write("데이터 주소와 인터넷 연결을 확인해 주세요.")
    st.exception(e)
    st.stop()

# -----------------------------------------------
# 3. 최신 연도 데이터 선택
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

latest_year = int(df["연도"].max())
df = df[df["연도"] == latest_year].copy()

# 지역 이름을 문자열로 통일합니다.
for col in ["시도", "시군구", "동"]:
    df[col] = df[col].fillna("").astype(str).str.strip()

df = df[
    (df["시도"] != "") &
    (df["시군구"] != "") &
    (df["동"] != "")
].copy()

# -----------------------------------------------
# 4. 연령별 인구 열 준비
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
    st.error("연령별 인구 열 일부를 찾을 수 없습니다.")
    st.write("누락된 열 예시:", missing_age_columns[:10])
    st.stop()

# 인구 열을 숫자형으로 변환합니다.
for col in needed_columns:
    df[col] = pd.to_numeric(
        df[col].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    ).fillna(0)

# -----------------------------------------------
# 5. 지역 선택
# 시도 → 시군구 → 동 순서
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

sigungu_df = sido_df[
    sido_df["시군구"] == selected_sigungu
]

with col3:
    dong_options = sorted(sigungu_df["동"].unique().tolist())
    selected_dong = st.selectbox("동", dong_options)

# -----------------------------------------------
# 6. 선택한 지역의 인구 계산
# -----------------------------------------------
selected_df = sigungu_df[
    sigungu_df["동"] == selected_dong
]

if selected_df.empty:
    st.warning("선택한 지역의 데이터가 없습니다.")
    st.stop()

male_population = (
    selected_df[male_columns]
    .sum(axis=0)
    .to_numpy(dtype=float)
).clip(min=0)

female_population = (
    selected_df[female_columns]
    .sum(axis=0)
    .to_numpy(dtype=float)
).clip(min=0)

age_population = male_population + female_population

male_total = int(male_population.sum())
female_total = int(female_population.sum())
total_population = male_total + female_total

# -----------------------------------------------
# 7. 핵심 지표 계산
# -----------------------------------------------

# 평균연령: 연령별 인구를 가중치로 계산합니다.
# 100세 이상은 계산상 100세로 처리합니다.
age_values = list(range(100)) + [100]

if total_population > 0:
    average_age = sum(
        age_values[i] * age_population[i]
        for i in range(len(age_values))
    ) / total_population
else:
    average_age = 0.0

# 고령화율: 전체 인구 중 65세 이상 인구 비율
elderly_population = int(age_population[65:].sum())

if total_population > 0:
    aging_rate = elderly_population / total_population * 100
else:
    aging_rate = 0.0

# 어린이 인구: 0~14세
child_population = int(age_population[:15].sum())

# -----------------------------------------------
# 8. 지표 카드 3개
# -----------------------------------------------
st.divider()

st.subheader(
    f"{selected_sido} {selected_sigungu} {selected_dong}"
)
st.caption(f"인구 기준 연도: {latest_year}년")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric("총인구", f"{total_population:,}명")

with card2:
    st.metric("평균연령", f"{average_age:.1f}세")

with card3:
    if aging_rate > 20:
        st.metric("고령화율 ⚠️ 주의", f"{aging_rate:.1f}%")
    else:
        st.metric("고령화율", f"{aging_rate:.1f}%")

if aging_rate > 20:
    st.warning(
        "이 지역의 고령화율이 20%를 초과합니다. "
        "65세 이상 인구가 전체 인구의 5분의 1보다 많습니다."
    )

# -----------------------------------------------
# 9. 인구 피라미드 그래프
# 남성은 왼쪽(음수), 여성은 오른쪽(양수)
# -----------------------------------------------
fig = go.Figure()

# 세로축의 숫자 좌표: 0부터 100까지
age_positions = list(range(101))

# 각 막대의 마우스 오버에 표시할 나이 라벨입니다.
# "0세", "1세", ..., "100세 이상"을 그대로 사용합니다.
male_hover_data = [
    [age_labels[i], male_population[i]]
    for i in range(101)
]

female_hover_data = [
    [age_labels[i], female_population[i]]
    for i in range(101)
]

# 남성 인구: 음수로 바꿔 왼쪽에 표시
fig.add_trace(go.Bar(
    x=-male_population,
    y=age_positions,
    orientation="h",
    name="남성",
    marker_color="#789BC2",
    customdata=male_hover_data,
    hovertemplate=(
        "나이: %{customdata[0]}<br>"
        "남성 인구: %{customdata[1]:,.0f}명"
        "<extra></extra>"
    )
))

# 여성 인구: 양수로 오른쪽에 표시
fig.add_trace(go.Bar(
    x=female_population,
    y=age_positions,
    orientation="h",
    name="여성",
    marker_color="#D98F96",
    customdata=female_hover_data,
    hovertemplate=(
        "나이: %{customdata[0]}<br>"
        "여성 인구: %{customdata[1]:,.0f}명"
        "<extra></extra>"
    )
))

# 가로축 범위를 양쪽 대칭으로 설정합니다.
max_population = max(
    float(male_population.max()),
    float(female_population.max()),
    1.0
)

axis_limit = max_population * 1.1
tick_step = axis_limit / 4

tick_values = [
    -axis_limit,
    -3 * tick_step,
    -2 * tick_step,
    -tick_step,
    0,
    tick_step,
    2 * tick_step,
    3 * tick_step,
    axis_limit
]

# 음수인 남성 인구도 눈금에는 양수로 표시합니다.
tick_text = [
    f"{abs(value):,.0f}" for value in tick_values
]

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
    margin=dict(l=90, r=35, t=90, b=70),
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
        tickmode="array",
        tickvals=tick_values,
        ticktext=tick_text,
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor="#9B8573",
        gridcolor="#EDE2D8"
    ),
    yaxis=dict(
        title="나이",
        tickmode="array",
        tickvals=age_positions,
        ticktext=age_labels,
        range=[-0.5, 100.5],
        dtick=5,
        gridcolor="#F0E7DE"
    )
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------
# 10. 그래프 아래 자동 설명
# -----------------------------------------------
st.subheader("우리 동네 인구 구성")

if total_population == 0:
    explanation = (
        "인구 자료가 없어 어린이와 어르신의 비중을 "
        "비교할 수 없습니다."
    )
elif child_population > elderly_population:
    explanation = (
        f"이 동네는 아이가 많은 편입니다. "
        f"0~14세 인구는 {child_population:,}명으로, "
        f"65세 이상 인구 {elderly_population:,}명보다 많습니다."
    )
elif elderly_population > child_population:
    explanation = (
        f"이 동네는 어르신이 많은 편입니다. "
        f"65세 이상 인구는 {elderly_population:,}명으로, "
        f"0~14세 인구 {child_population:,}명보다 많습니다."
    )
else:
    explanation = (
        f"이 동네는 어린이 인구와 어르신 인구가 같습니다. "
        f"두 연령층 모두 {child_population:,}명입니다."
    )

st.info(explanation)

# -----------------------------------------------
# 11. 연령별 상세 표
# -----------------------------------------------
with st.expander("연령별 남녀 인구 상세 표"):
    detail_df = pd.DataFrame({
        "나이": age_labels,
        "남성 인구": male_population.astype(int),
        "여성 인구": female_population.astype(int),
        "전체 인구": age_population.astype(int)
    })

    st.dataframe(
        detail_df,
        use_container_width=True,
        hide_index=True
    )

# -----------------------------------------------
# 12. 지표 계산 기준 안내
# -----------------------------------------------
with st.expander("지표 계산 기준 보기"):
    st.write(
        "- 총인구: 연령별 남녀 인구의 합계\n"
        "- 평균연령: 연령별 인구 가중평균. "
        "100세 이상은 계산상 100세로 처리\n"
        "- 고령화율: 65세 이상 인구 ÷ 총인구 × 100\n"
        "- 어린이 인구: 0~14세 인구\n"
        "- 어르신 인구: 65세 이상 인구\n"
        "- 주의 표시: 고령화율이 20%를 초과하는 경우"
    )

st.caption(
    "자료 출처: 지정된 GitHub 인구 데이터 파일"
)
