import streamlit as st
import pandas as pd
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="어제의 영화 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 어제의 영화 박스오피스")
st.caption("KOBIS 영화관입장권통합전산망 일별 박스오피스")


# ---------------------------------------------------------
# 한국 시간 기준으로 '어제' 날짜 만들기
# ---------------------------------------------------------
def get_yesterday_korea():
    """한국 시간(Asia/Seoul)을 기준으로 어제 날짜를 yyyymmdd 형식으로 반환합니다."""

    korea_now = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday = korea_now - timedelta(days=1)

    return yesterday.strftime("%Y%m%d")


# ---------------------------------------------------------
# API에서 받아온 숫자 문자열을 숫자로 바꾸기
# ---------------------------------------------------------
def to_int(value):
    """API에서 문자열로 오는 숫자를 안전하게 정수로 변환합니다."""

    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------
# KOBIS API 호출
#
# cache_data를 사용하면 같은 날짜의 결과를 약 1시간 동안
# 기억해서 API를 반복 호출하지 않습니다.
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_boxoffice(target_date, api_key):
    """
    KOBIS 일별 박스오피스 API를 호출합니다.

    반환값:
    - 성공: (데이터프레임, None)
    - 실패: (None, 오류 메시지)
    """

    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_date,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        # HTTP 상태 코드 오류 확인
        response.raise_for_status()

        data = response.json()

    except requests.exceptions.Timeout:
        return None, "API 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 보세요."

    except requests.exceptions.RequestException as e:
        return None, f"API 요청에 실패했습니다. 인터넷 연결과 API 상태를 확인해 보세요.\n\n{e}"

    except ValueError:
        return None, "API 응답을 읽지 못했습니다. KOBIS 서버 응답 형식을 확인해 보세요."

    # -----------------------------------------------------
    # KOBIS는 인증키 오류 등이 발생해도 HTTP 200을 줄 수 있으므로
    # faultInfo 상자가 있는지 반드시 확인합니다.
    # -----------------------------------------------------
    if "faultInfo" in data:
        fault_info = data["faultInfo"]

        # faultInfo의 구조가 달라도 가능한 내용을 보여 주기 위해 처리
        if isinstance(fault_info, dict):
            message = (
                fault_info.get("message")
                or fault_info.get("faultString")
                or str(fault_info)
            )
        else:
            message = str(fault_info)

        return None, (
            "KOBIS API에서 오류를 반환했습니다.\n\n"
            f"오류 내용: {message}\n\n"
            "확인할 사항:\n"
            "1. Streamlit Secrets의 KOBIS_KEY가 올바른지 확인하세요.\n"
            "2. KOBIS Open API 인증키가 정상적으로 발급되어 있는지 확인하세요.\n"
            "3. API 요청 주소와 사용량 제한을 확인하세요."
        )

    # boxOfficeResult 확인
    boxoffice_result = data.get("boxOfficeResult")

    if not boxoffice_result:
        return None, (
            "박스오피스 데이터를 찾지 못했습니다.\n\n"
            "확인할 사항:\n"
            "1. API 인증키(KOBIS_KEY)가 올바른지 확인하세요.\n"
            "2. KOBIS API가 정상적으로 응답하는지 확인하세요.\n"
            "3. 해당 날짜의 박스오피스 데이터가 집계되었는지 확인하세요."
        )

    # 영화 목록 가져오기
    movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

    # 목록이 비어 있는 경우
    if not movie_list:
        return None, (
            f"{target_date} 날짜의 영화 목록이 비어 있습니다.\n\n"
            "확인할 사항:\n"
            "1. 조회 날짜가 올바른지 확인하세요.\n"
            "2. 해당 날짜의 박스오피스가 아직 집계되지 않았을 수 있습니다.\n"
            "3. KOBIS API의 일시적인 문제인지 잠시 후 다시 확인하세요."
        )

    # -----------------------------------------------------
    # 필요한 데이터만 골라서 데이터프레임으로 만들기
    # 숫자로 오는 문자열은 int로 변환합니다.
    # -----------------------------------------------------
    rows = []

    for movie in movie_list:
        rows.append(
            {
                "순위": to_int(movie.get("rank")),
                "영화명": movie.get("movieNm", ""),
                "개봉일": movie.get("openDt", ""),
                "관객수": to_int(movie.get("audiCnt")),
                "누적관객": to_int(movie.get("audiAcc")),
                "스크린수": to_int(movie.get("scrnCnt")),
            }
        )

    df = pd.DataFrame(rows)

    # 순위를 숫자로 정렬
    df = df.sort_values("순위").reset_index(drop=True)

    return df, None


# ---------------------------------------------------------
# Secrets에서 인증키 가져오기
# ---------------------------------------------------------
try:
    KOBIS_KEY = st.secrets["KOBIS_KEY"]

except KeyError:
    st.error(
        "🔑 KOBIS 인증키를 찾을 수 없습니다.\n\n"
        "Streamlit Cloud의 Secrets에 다음과 같이 설정했는지 확인하세요.\n\n"
        "KOBIS_KEY = \"발급받은_인증키\""
    )
    st.stop()


# ---------------------------------------------------------
# 어제 날짜 계산 후 데이터 조회
# ---------------------------------------------------------
target_date = get_yesterday_korea()

# 화면에 보기 좋은 날짜
display_date = datetime.strptime(
    target_date,
    "%Y%m%d"
).strftime("%Y년 %m월 %d일")

st.subheader(f"📅 {display_date} 기준")

df, error_message = get_boxoffice(target_date, KOBIS_KEY)


# ---------------------------------------------------------
# 오류가 발생했을 때 안내 메시지 표시
# ---------------------------------------------------------
if error_message:
    st.error(error_message)
    st.stop()


# ---------------------------------------------------------
# 1위 영화 정보
# ---------------------------------------------------------
top_movie = df.iloc[0]

st.divider()
st.subheader(f"🥇 오늘의 1위: {top_movie['영화명']}")

# 지표 카드 3개
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="👥 어제 관객수",
        value=f"{top_movie['관객수']:,}명",
    )

with col2:
    st.metric(
        label="🎟️ 누적 관객수",
        value=f"{top_movie['누적관객']:,}명",
    )

with col3:
    st.metric(
        label="🖥️ 스크린수",
        value=f"{top_movie['스크린수']:,}개",
    )


# ---------------------------------------------------------
# 관객수 상위 5편 막대그래프
# ---------------------------------------------------------
st.divider()
st.subheader("📊 관객수 상위 5편")

top5 = (
    df.sort_values("관객수", ascending=False)
    .head(5)
    .set_index("영화명")
)

st.bar_chart(top5["관객수"])


# ---------------------------------------------------------
# 전체 박스오피스 표
# ---------------------------------------------------------
st.divider()
st.subheader("📋 전체 박스오피스")

# 숫자를 보기 좋게 표시하기 위한 복사본
display_df = df.copy()

display_df["관객수"] = display_df["관객수"].map(
    lambda x: f"{x:,}"
)

display_df["누적관객"] = display_df["누적관객"].map(
    lambda x: f"{x:,}"
)

display_df["스크린수"] = display_df["스크린수"].map(
    lambda x: f"{x:,}"
)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
)


# ---------------------------------------------------------
# 아래쪽 안내 문구
# ---------------------------------------------------------
st.caption(
    "※ 데이터 출처: KOBIS 영화관입장권통합전산망 Open API"
)
