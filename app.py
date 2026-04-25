import streamlit as st
import json
import requests
import random

# ─────────────────────────────────────────────
# 1. 설정 및 보안 (Secrets 사용)
# ─────────────────────────────────────────────
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Streamlit Cloud 설정(Secrets)에서 'GEMINI_API_KEY'를 추가해 주세요.")
    st.stop()

st.set_page_config(page_title="🧠 딴생각 AI", layout="wide")

# ─────────────────────────────────────────────
# 2. 디자인 (CSS)
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
  .label { font-size: 12px; margin-left: 15px; color: #555; }
  .label.user { text-align: right; margin-right: 15px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# 3. 로직 및 상태 관리
# ─────────────────────────────────────────────
DAYDREAM_PROB = {1:0.10, 2:0.30, 3:0.50, 4:0.75, 5:0.95}
BLEED_PROB    = {1:0.00, 2:0.05, 3:0.15, 4:0.40, 5:0.85}
STATUS_INFO = {
    1: ("🙂", "정상",       "#1EB92A", "#FFFFFF"),
    2: ("😟", "살짝 멍함", "#ffc400", "#000000"),
    3: ("🤕", "집중력 저하", "#ff7300", "#FFFFFF"),
    4: ("🤯", "혼란스러움", "#df054eb8", "#FFFFFF"),
    5: ("🤪", "안드로메다", "#ff0000", "#FFFFFF"),
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "distract_level" not in st.session_state:
    st.session_state.distract_level = 3

with st.sidebar:
    st.markdown("## 🧠 AI 제어판")
    level = st.slider("🎚️ 딴생각 강도", 1, 5, st.session_state.distract_level)
    st.session_state.distract_level = level
    emoji, txt, bg, fg = STATUS_INFO[level]
    st.markdown(f'<div class="status-card" style="background:{bg};color:{fg};">{emoji} 상태: {txt}</div>', unsafe_allow_html=True)
    
    if st.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

# ─────────────────────────────────────────────
# 4. 프롬프트 및 API 호출 (v1beta 대응)
# ─────────────────────────────────────────────
def get_system_instruction(mode):
    base_instruction = (
        "당신은 유능한 AI 조수입니다. 하지만 가끔 딴생각에 빠집니다. "
        "반드시 다음 JSON 형식으로만 답변하세요: "
        "{\"answer\": \"사용자 질문에 대한 답변\", \"thought_flow\": [\"생각의 흐름1\", \"생각의 흐름2\"], \"dream_text\": \"딴생각 내용\"}"
    )
    if mode == "normal":
        return base_instruction + " 질문에 집중해서 친절하게 답변하세요."
    elif mode == "daydream":
        return base_instruction + " 답변은 하되, dream_text에는 질문에서 파생된 아주 엉뚱하고 기발한 상상을 적으세요."
    else: # bleed
        return base_instruction + " 딴생각이 너무 심해져서 answer 필드에도 헛소리나 문맥에 맞지 않는 말이 섞여 나오게 하세요."

def call_gemini(user_prompt, history, mode):
    # v1beta 경로가 시스템 인스트럭션 처리에 더 안정적입니다.
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={GEMINI_API_KEY}"

    gemini_history = []
    for m in history[-6:]:
        role = "user" if m["role"] == "user" else "model"
        # 이전 답변이 JSON일 경우 answer 텍스트만 추출해서 전달
        content = m["content"] if m["role"] == "user" else m.get("answer", "...")
        gemini_history.append({"role": role, "parts": [{"text": content}]})
    
    # 현재 사용자 메시지 추가
    gemini_history.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload = {
        "contents": gemini_history,
        "system_instruction": {
            "parts": [{"text": get_system_instruction(mode)}]
        },
        "generationConfig": {
            "temperature": 1.0,
            "response_mime_type": "application/json"
        }
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            return json.loads(resp.json()['candidates'][0]['content']['parts'][0]['text'])
        else:
            # 400 에러 등의 경우 상세 메시지 출력 (디버깅용)
            error_msg = resp.json().get("error", {}).get("message", "알 수 없는 오류")
            return {"answer": f"에러 발생: {error_msg}", "thought_flow": ["오류 발생"], "dream_text": "회로에 노이즈가 발생했습니다."}
    except Exception as e:
        return {"answer": "서버 연결에 실패했습니다.", "thought_flow": ["네트워크 에러"], "dream_text": str(e)}

# ─────────────────────────────────────────────
# 5. 메인 UI 및 채팅 실행
# ─────────────────────────────────────────────
st.markdown('<div style="background:#7c5cbf;padding:14px 20px;border-radius:0 0 12px 12px;color:white;font-weight:bold;font-size:20px;">🧠 딴생각 AI (Gemini Flash)</div>', unsafe_allow_html=True)

# 메시지 출력 루프
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="label user">나</div><div class="bubble-wrap user"><div class="bubble user">{msg["content"]}</div></div>', unsafe_allow_html=True)
    else:
        bubble_class = "bleed" if msg.get("bleed") else "ai"
        st.markdown(f'<div class="label ai">AI</div><div class="bubble-wrap"><div class="avatar" style="width:36px;height:36px;border-radius:50%;background:#7c5cbf;color:white;display:flex;align-items:center;justify-content:center;margin-right:8px;">🤖</div><div class="bubble {bubble_class}">{msg.get("answer", "")}</div></div>', unsafe_allow_html=True)
        if msg.get("has_dream"):
            flow = " ➜ ".join(msg.get("thought_flow", []))
            st.markdown(f'<div class="thought-flow">💭 {flow}</div><div class="daydream-panel"><div class="dptitle">🌀 딴생각 중...</div>{msg.get("dream_text")}</div>', unsafe_allow_html=True)

# 채팅 입력창
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 1. 사용자 메시지 추가 및 화면 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun() # 입력을 즉시 반영하기 위해 리런

# 답변 생성 로직 (세션 상태를 체크하여 답변이 필요한 경우 실행)
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    lv = st.session_state.distract_level
    r = random.random()
    
    # 확률에 따른 모드 결정
    if r < DAYDREAM_PROB[lv] * BLEED_PROB[lv]: mode, has_dream, is_bleed = "bleed", True, True
    elif r < DAYDREAM_PROB[lv]: mode, has_dream, is_bleed = "daydream", True, False
    else: mode, has_dream, is_bleed = "normal", False, False
    
    with st.spinner("생각 중..."):
        user_input = st.session_state.messages[-1]["content"]
        res = call_gemini(user_input, st.session_state.messages[:-1], mode)
        res["role"], res["has_dream"], res["bleed"] = "ai", has_dream, is_bleed
        st.session_state.messages.append(res)
    st.rerun()
