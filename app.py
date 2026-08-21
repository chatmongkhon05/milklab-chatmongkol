"""EasyMart RAG Chatbot (S4 - Pivot).

Run locally: streamlit run app.py
Deploy: push to GitHub then Actions deploys to HuggingFace Space
"""

import json
import os
import time
import uuid

import numpy as np
import streamlit as st


def chunk_markdown(text: str) -> list[str]:
    """Split markdown knowledge base into contextual chunks."""
    sections = text.split("\n\n")
    chunks = []
    current_header = ""

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue

        lines = [line.strip() for line in sec.split("\n") if line.strip()]
        if not lines:
            continue

        # Header section tracking
        if lines[0].startswith("#"):
            current_header = lines[0].lstrip("#").strip()
            # If section has body lines under header
            body_lines = lines[1:]
            if not body_lines:
                continue
            lines = body_lines

        header_prefix = f"[{current_header}] " if current_header else ""

        # Check if list items
        if any(line.startswith("- ") or line.startswith("**") for line in lines):
            for line in lines:
                chunks.append(f"{header_prefix}{line}")
        else:
            chunks.append(f"{header_prefix}{' '.join(lines)}")

    return chunks


@st.cache_resource
def load_index():
    """โหลด easymart_kb.md, split เป็น chunk, encode ด้วย Google gemini-embedding-001,
    สร้าง faiss index. ใช้ Google API เพื่อรองรับภาษาไทยได้ดี

    Returns: (embed_fn, index, chunks_list)
    """
    import faiss
    from google import genai
    from dotenv import load_dotenv
    load_dotenv()

    kb_path = "easymart_kb.md"
    if not os.path.exists(kb_path):
        kb_path = "pet_kb.md"  # Fallback
    if not os.path.exists(kb_path):
        raise FileNotFoundError("Knowledge base file 'easymart_kb.md' not found.")

    with open(kb_path, "r", encoding="utf-8") as f:
        content = f.read()

    chunks = chunk_markdown(content)

    api_key = os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)

    # Encode chunks ด้วย Google gemini-embedding-001 (รองรับภาษาไทย)
    result = client.models.embed_content(
        model="models/gemini-embedding-001",
        contents=chunks,
    )
    embeddings = np.array([e.values for e in result.embeddings], dtype=np.float32)

    # Normalize สำหรับ cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.where(norms == 0, 1, norms)

    # Create FAISS Index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    # embed_fn: ฟังก์ชัน helper สำหรับ encode query ด้วย API เดียวกัน
    def embed_fn(text: str) -> np.ndarray:
        r = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=[text],
        )
        vec = np.array(r.embeddings[0].values, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return (vec / norm if norm > 0 else vec).reshape(1, -1)

    return embed_fn, index, chunks


def log_span(trace_id: str, span_name: str, duration_ms: float, inputs: dict, outputs: dict) -> dict:
    """Log trace span for observability."""
    record = {
        "trace_id": trace_id,
        "span_name": span_name,
        "duration_ms": round(duration_ms, 2),
        "inputs": inputs,
        "outputs": outputs,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with open("traces.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return record


def retrieve_top_k(query: str, embed_fn, index, chunks: list[str], k: int = 3, trace_id: str | None = None) -> list[str]:
    """encode query ด้วย Google Embedding API, search FAISS, return top-k chunks"""
    start_time = time.time()

    # Encode query ด้วย embed_fn (Google gemini-embedding-001)
    q_emb = embed_fn(query)

    # Search FAISS index
    scores, indices = index.search(q_emb, k)

    retrieved = [chunks[idx] for idx in indices[0] if 0 <= idx < len(chunks)]
    retrieved_scores = [float(score) for score in scores[0]]

    duration_ms = (time.time() - start_time) * 1000
    if trace_id:
        log_span(
            trace_id=trace_id,
            span_name="retrieve_top_k",
            duration_ms=duration_ms,
            inputs={"query": query, "k": k},
            outputs={"retrieved_count": len(retrieved), "scores": retrieved_scores, "chunks": retrieved},
        )

    return retrieved


def generate_answer(query: str, context_chunks: list[str], trace_id: str | None = None) -> str:
    """ส่ง query + context ไป Gemini, return answer พร้อม log span"""
    from google import genai
    from dotenv import load_dotenv

    start_time = time.time()
    load_dotenv()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        err_msg = "ERROR: GOOGLE_API_KEY ไม่ได้ตั้งค่าในสภาพแวดล้อมหรือไฟล์ .env"
        if trace_id:
            log_span(trace_id, "generate_answer", 0.0, {"query": query}, {"error": err_msg})
        return err_msg

    client = genai.Client(api_key=api_key)
    context_text = "\n".join(f"- {c}" for c in context_chunks)

    prompt = (
        "คุณคือ AI Assistant ประจำร้าน EasyMart ร้านขายของชำมินิมาร์ทชุมชนออนไลน์\n"
        "ให้ตอบคำถามของลูกค้าโดยใช้ข้อมูลใน Context ต่อไปนี้เท่านั้น\n"
        "ตอบอย่างสุภาพ อบอุ่น เป็นกันเอง ชัดเจน และถูกต้องตามข้อมูลใน Context\n"
        "หากใน Context ไม่มีข้อมูลที่ใช้ตอบคำถาม ให้ตอบว่าไม่ทราบข้อมูลหรือไม่พบข้อมูลในระบบ\n\n"
        f"Context:\n{context_text}\n\n"
        f"คำถาม: {query}\n"
        "คำตอบ:"
    )

    models_to_try = [
        os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-3.5-flash-lite",
        "gemini-1.5-flash",
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    answer = ""
    used_model = models_to_try[0]
    last_exc = None

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                answer = response.text.strip()
                used_model = model_name
                break
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "404" in err_str or "NOT_FOUND" in err_str:
                time.sleep(1)
                continue
            break

    if not answer:
        if last_exc:
            err_str = str(last_exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                answer = "ขณะนี้โควตาการใช้งาน Gemini API เต็มชั่วคราว (429 Rate Limit) กรุณารอ 30-60 วินาที แล้วลองถามใหม่อีกครั้งครับ"
            else:
                answer = f"เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gemini: {last_exc}"
        else:
            answer = "ไม่มีคำตอบจากระบบ"

    duration_ms = (time.time() - start_time) * 1000
    if trace_id:
        log_span(
            trace_id=trace_id,
            span_name="generate_answer",
            duration_ms=duration_ms,
            inputs={"query": query, "model": used_model, "context_count": len(context_chunks)},
            outputs={"answer": answer},
        )

    return answer


def apply_custom_styles():
    """Inject custom CSS stylesheet for EasyMart modern aesthetic theme."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Prompt', 'Inter', sans-serif;
        }

        /* Main Container background & padding */
        .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 3rem;
            max-width: 900px;
        }

        /* EasyMart Hero Header Card */
        .easymart-header {
            background: linear-gradient(135deg, #059669 0%, #10b981 60%, #34d399 100%);
            border-radius: 20px;
            padding: 24px 30px;
            color: white;
            box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.35);
            margin-bottom: 25px;
            position: relative;
            overflow: hidden;
        }

        .easymart-header::after {
            content: "🛒";
            position: absolute;
            right: 20px;
            bottom: -15px;
            font-size: 110px;
            opacity: 0.18;
            transform: rotate(-15deg);
        }

        .easymart-title {
            font-size: 2.2rem;
            font-weight: 700;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 12px;
            letter-spacing: -0.5px;
        }

        .easymart-subtitle {
            font-size: 1.05rem;
            font-weight: 400;
            margin-top: 8px;
            opacity: 0.95;
            line-height: 1.5;
        }

        .easymart-badge {
            display: inline-flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.22);
            backdrop-filter: blur(10px);
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
            margin-top: 12px;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }

        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%);
            border-right: 1px solid #e5e7eb;
        }

        .sidebar-box {
            background: white;
            border-radius: 14px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
        }

        .promo-banner {
            background: linear-gradient(135deg, #fffbe6 0%, #fef3c7 100%);
            border-left: 4px solid #f59e0b;
            padding: 12px 14px;
            border-radius: 8px;
            margin-top: 10px;
            font-size: 0.9rem;
            color: #92400e;
        }

        /* Quick Prompt Buttons Styling */
        .stButton button {
            border-radius: 12px !important;
            border: 1px solid #d1fae5 !important;
            background-color: #ecfdf5 !important;
            color: #047857 !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            padding: 8px 16px !important;
            transition: all 0.2s ease-in-out !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02) !important;
        }

        .stButton button:hover {
            background-color: #10b981 !important;
            color: white !important;
            border-color: #10b981 !important;
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25) !important;
        }

        /* Chat Message Bubbles */
        [data-testid="stChatMessage"] {
            border-radius: 16px;
            padding: 14px 18px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        }

        /* Expanders Styling */
        .stExpander {
            border-radius: 12px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 2px 6px rgba(0,0,0,0.02) !important;
            margin-top: 8px !important;
            overflow: hidden;
        }

        /* Footer */
        .easymart-footer {
            text-align: center;
            color: #9ca3af;
            font-size: 0.85rem;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #f3f4f6;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(
        page_title="EasyMart RAG Chatbot 🛒",
        page_icon="🛒",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    # Apply Custom EasyMart Styling
    apply_custom_styles()

    # Load RAG Index
    try:
        embed_fn, index, chunks = load_index()
    except NotImplementedError as exc:
        st.error(f"TODO not implemented: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"เกิดข้อผิดพลาดในการโหลด Index: {exc}")
        st.stop()

    # --- SIDEBAR CONTENT ---
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align: center; padding: 10px 0;">
                <h2 style="color: #059669; margin: 0; font-size: 1.6rem; font-weight: 700;">EasyMart 🛒</h2>
                <p style="color: #6b7280; font-size: 0.9rem; margin-top: 4px;">ร้านขายของชำออนไลน์มินิมาร์ทชุมชน</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="sidebar-box">
                <div style="font-weight: 600; color: #1f2937; margin-bottom: 8px;">⏰ เวลาทำการร้าน</div>
                <div style="font-size: 0.9rem; color: #4b5563;">เปิดบริการทุกวัน <b>07:00 - 21:00 น.</b></div>
                <div style="margin-top: 6px; font-size: 0.85rem; color: #059669; font-weight: 500;">
                    🟢 สถานะ: พร้อมรับออเดอร์
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="sidebar-box">
                <div style="font-weight: 600; color: #1f2937; margin-bottom: 8px;">📦 หมวดหมู่สินค้าฮิต</div>
                <div style="font-size: 0.88rem; color: #4b5563; line-height: 1.8;">
                    🥤 <b>เครื่องดื่ม:</b> น้ำดื่ม, นม UHT, กาแฟ<br>
                    🌾 <b>อาหารแห้ง:</b> ข้าวสารหอมมะลิ 5kg<br>
                    🍜 <b>บะหมี่:</b> ต้มยำกุ้ง, เครื่องปรุง<br>
                    🧼 <b>ของใช้:</b> ผงซักฟอก, น้ำยาล้างจาน
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="promo-banner">
                <b>⚡ โปรโมชั่นพิเศษ!</b><br>
                ซื้อสินค้าครบ <b>300 บาท</b> จัดส่งฟรีด่วนถึงบ้านทันที (ปกติค่าส่ง 25 บาท)
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ ล้างประวัติการสนทนา", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # --- HERO HEADER ---
    st.markdown(
        """
        <div class="easymart-header">
            <h1 class="easymart-title">EasyMart RAG Chatbot 🛒</h1>
            <div class="easymart-subtitle">
                ผู้ช่วย AI ประจำร้านขายของชำ EasyMart ตอบคำถามสินค้า เช็กราคา สั่งซื้อ และข้อมูลบริการ
            </div>
            <div class="easymart-badge">
                ✨ ขับเคลื่อนด้วย Google Gemini & FAISS Vector RAG
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Quick Suggestion Prompts
    st.markdown("<div style='font-size: 0.9rem; font-weight: 600; color: #374151; margin-bottom: 8px;'>💡 คำถามที่พบบ่อย (คลิกเพื่อถาม):</div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    
    quick_query = None
    with col1:
        if st.button("🌾 ข้าวสาร 5kg กี่บาท", use_container_width=True):
            quick_query = "ข้าวสารหอมมะลิ 5kg ราคาเท่าไหร่"
    with col2:
        if st.button("🚚 ค่าจัดส่งกี่บาท", use_container_width=True):
            quick_query = "คิดค่าจัดส่งยังไง ส่งฟรีเมื่อซื้อเท่าไหร่"
    with col3:
        if st.button("🎁 มีโปรโมชั่นอะไรบ้าง", use_container_width=True):
            quick_query = "มีโปรโมชั่นพิเศษอะไรบ้างตอนนี้"
    with col4:
        if st.button("⏰ ร้านเปิดกี่โมง", use_container_width=True):
            quick_query = "ร้าน EasyMart เปิดให้บริการกี่โมงถึงกี่โมง"

    # Chat history state initialization
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "สวัสดีครับ! ยินดีต้อนรับสู่ร้านขายของชำ **EasyMart 🛒** มีอะไรให้ผู้ช่วย AI ช่วยค้นข้อมูลสินค้า เช็กราคา หรือข้อมูลการจัดส่งสอบถามได้เลยครับ!",
            }
        ]

    # Render Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🛒" if msg["role"] == "assistant" else "👤"):
            st.write(msg["content"])

    # User Input Processing (from chat input or quick suggestion button)
    user_prompt = st.chat_input("ถามเกี่ยวกับสินค้า ราคา หรือบริการของ EasyMart...")
    prompt_to_process = quick_query or user_prompt

    if prompt_to_process:
        st.session_state.messages.append({"role": "user", "content": prompt_to_process})
        with st.chat_message("user", avatar="👤"):
            st.write(prompt_to_process)

        with st.chat_message("assistant", avatar="🛒"):
            with st.spinner("กำลังค้นข้อมูลสินค้า EasyMart..."):
                trace_id = str(uuid.uuid4())
                start_retrieve = time.time()
                context = retrieve_top_k(prompt_to_process, embed_fn, index, chunks, k=3, trace_id=trace_id)
                retrieve_time = (time.time() - start_retrieve) * 1000

                start_gen = time.time()
                answer = generate_answer(prompt_to_process, context, trace_id=trace_id)
                gen_time = (time.time() - start_gen) * 1000

            st.write(answer)

            # Styled Source Chunks Expander
            with st.expander("📚 ข้อมูลอ้างอิงจากคลังสินค้า (Source Chunks)"):
                for i, c in enumerate(context, 1):
                    st.markdown(f"**[{i}]** `{c}`")

            # Styled Observability Trace Expander
            with st.expander("⚡ ประสิทธิภาพการประมวลผล (Observability Trace)"):
                st.json({
                    "trace_id": trace_id,
                    "retrieval_time_ms": round(retrieve_time, 2),
                    "generation_time_ms": round(gen_time, 2),
                    "total_latency_ms": round(retrieve_time + gen_time, 2),
                    "chunks_retrieved": len(context),
                })

        st.session_state.messages.append({"role": "assistant", "content": answer})

    # Footer
    st.markdown(
        """
        <div class="easymart-footer">
            © 2026 <b>EasyMart Online Grocery Store</b> — Solopreneurs AI Pivot & Polish (Session 4)
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
