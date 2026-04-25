import streamlit as st
import json
import requests
import random

# ─────────────────────────────────────────────
# 설정 (보안을 위해 st.secrets 사용)
# ─────────────────────────────────────────────
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Secrets 설정에서 'GEMINI_API_KEY'를 찾을 수 없습니다. Streamlit Cloud 설정의 Secrets 탭에 'GEMINI_API_KEY'를 추가해 주세요.")
    st.stop()

st.set_page_config(page_title="🧠 딴생각 AI", layout="wide")

# ─────────────────────────────────────────────
# CSS (디자인 유지 및 개선)
# ─────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #b2c7d9; }
  .bubble-wrap { display:flex; margin:6px 12px; align-items:flex-end; gap:8px; }
  .bubble-wrap.user { flex-direction:row-reverse; }
  .bubble {
    max-width:65%; padding:10px 14px; border-radius:18px;
    font-size:14px; line-height:1.6; word-break:break-word; white-space:pre-wrap;
  }
  .bubble.user  { background:#fee500; border-bottom-right-radius:4px; color:#000; }
  .bubble.ai    { background:#ffffff; border-bottom-left-radius:4px;  color:#000; }
  .bubble.bleed {
    background:#fff3e0; border-bottom-left-radius:4px; color:#7c4e00;
    border-left:3px solid #ff9800; font-style:italic;
  }
  .daydream-panel {
    margin:4px 12px 10px 50px;
    background:linear-gradient(135deg,#f3e8ff,#ede0ff);
    border:1px dashed #b08ee0; border-radius:12px;
    padding:10px 14px; font-size:13px; color:#5a3d8a; font-style:italic;
  }
  .daydream-panel .dptitle {
    font-size:11px; font-weight:bold; color:#9b6ee0;
    margin-bottom:6px; font-style:normal; letter-spacing:.5px;
  }
  .thought-flow {
    font-size:11px; color:#8e6bbf; margin:2px 0 4px 50px;
    font-family:monospace; opacity:.85;
  }
  .status-card {
    border-radius:12px; padding:12px 16px; text-align:center;
    font-size:15px; font-weight:bold; margin-top:4px;
  }
  section[data-testid="stSidebar"]{ background:#1e1e2e; }
  section[data-testid="stSidebar"] * { color:white !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 로직 상수 및 상태 관리
# ─────────────────────────────────────────────
DAYDREAM_PROB = {1:0.40, 2:0.50, 3:0.60, 4:0.75, 5:0.90}
BLEED_PROB    = {1:0.00, 2:0.05, 3:0.10, 4:0.40, 5:0.80}
STATUS_INFO = {
    1: ("🙂", "정상",        "#1EB92A", "#FFFFFF"),
    2: ("😟", "살짝 머리 아픔", "#ffc400", "#000000"),
    3: ("🤕", "조금 아프다",   "#ff7300", "#FFFFFF"),
    4: ("🤯", "마니 아프다",   "#df054eb8", "#FFFFFF"),
    5: ("🤪", "헤헤헿ㅎㅎ",   "#ff0000", "#FFFFFF"),
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "distract_level" not in st.session_state:
    st.session_state.distract_level = 3

with st.sidebar:
    st.markdown("## 🧠 AI의 딴생각 설정")
    level = st.slider("🎚️ 딴생각 강도", 1, 5, st.session_state.distract_level)
    st.session_state.distract_level = level
    
    emoji, txt, bg, fg = STATUS_INFO[level]
    st.markdown(f'<div class="status-card" style="background:{bg};color:{fg};">{emoji} AI 상태: {txt}</div>', unsafe_allow_html=True)
    
    if st.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

# ─────────────────────────────────────────────
# 시스템 프롬프트 정의
# ─────────────────────────────────────────────
def get_system(mode):
    base = "당신은 유능한 AI입니다. 반드시 마크다운 없이 순수 JSON만 출력하세요. 형식: {\"answer\": \"...\", \"thought_flow\": [\"단계1\", \"단계2\"], \"dream_text\": \"...\"}"
    if mode == "normal":
        return base + " 사용자의 질문에 충실하게 답변하세요."
    elif mode == "daydream":
        return base + " 답변은 하되, dream_text에는 질문과 관련된 아주 엉뚱한 상상을 적으세요."
    else: # bleed
        return base + " 딴생각이 너무 심해서 answer 필드에도 헛소리나 딴생각이 섞여 나와야 합니다."

# ─────────────────────────────────────────────
# Gemini API 호출 함수
# ─────────────────────────────────────────────
def call_gemini(user_prompt, history, mode):
    # 안정적인 v1 API 경로 사용
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-3-flash-preview:generateContent?key={GEMINI_API_KEY}"

    gemini_history = []
    for m in history[-6:]: # 최근 대화 요약 전달
        role = "user" if m["role"] == "user" else "model"
        content = m["content"] if m["role"] == "user" else m.get("answer", "")
        gemini_history.append({"role": role, "parts": [{"text": content}]})
    gemini_history.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload = {
        "contents": gemini_history,
        "system_instruction": {"parts": [{"text": get_system(mode)}]},
        "generationConfig": {
            "temperature": 1.0,
            "response_mime_type": "application/json"
        }
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            return json.loads(resp.json()['candidates'][0]['content']['parts'][0]['text'])
        else:
            return {"answer": f"API 오류가 발생했습니다. (Code: {resp.status_code})", "thought_flow": ["오류"], "dream_text": "회로가 꼬였어요."}
    except Exception as e:
        return {"answer": f"연결 오류: {str(e)}", "thought_flow": ["에러"], "dream_text": "서버와 연결이 끊겼습니다."}

# ─────────────────────────────────────────────
# 메인 UI 및 채팅 로직
# ─────────────────────────────────────────────
st.markdown('<div style="background:#7c5cbf;padding:14px 20px;border-radius:0 0 12px 12px;color:white;font-weight:bold;font-size:20px;">🧠 딴생각 AI (Flash)</div>', unsafe_allow_html=True)

# 대화 기록 렌더링
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="label user">나</div><div class="bubble-wrap user"><div class="bubble user">{msg["content"]}</div></div>', unsafe_allow_html=True)
    else:
        bubble_class = "bleed" if msg.get("bleed") else "ai"
        st.markdown(f'<div class="label ai">🧠 AI</div><div class="bubble-wrap"><div class="avatar" style="width:36px;height:36px;border-radius:50%;background:#7c5cbf;color:white;display:flex;align-items:center;justify-content:center;margin-right:8px;">🤖</div><div class="bubble {bubble_class}">{msg.get("answer", "")}</div></div>', unsafe_allow_html=True)
        if msg.get("has_dream"):
            flow = " ➜ ".join(msg.get("thought_flow", []))
            st.markdown(f'<div class="thought-flow">💭 {flow}</div><div class="daydream-panel"><div class="dptitle">🌀 딴생각</div>{msg.get("dream_text")}</div>', unsafe_allow_html=True)

# 채팅 입력
if prompt := st.chat_input("메시지를 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 확률에 따른 모드 결정
    lv = st.session_state.distract_level
    r = random.random()
    if r < DAYDREAM_PROB[lv] * BLEED_PROB[lv]: mode, has_dream, is_bleed = "bleed", True, True
    elif r < DAYDREAM_PROB[lv]: mode, has_dream, is_bleed = "daydream", True, False
    else: mode, has_dream, is_bleed = "normal", False, False
    
    with st.spinner("생각 중..."):
        res = call_gemini(prompt, st.session_state.messages[:-1], mode)
        res["role"], res["has_dream"], res["bleed"] = "ai", has_dream, is_bleed
        st.session_state.messages.append(res)
    st.rerun()
