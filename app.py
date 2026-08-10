"""EasyMart RAG Chatbot (S3).

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
    """โหลด menu_kb.md, split เป็น chunk, encode ด้วย Google text-embedding-004,
    สร้าง faiss index. ใช้ Google API เพื่อรองรับภาษาไทยได้ดี

    Returns: (embed_fn, index, chunks_list)
    """
    import faiss
    from google import genai
    from dotenv import load_dotenv
    load_dotenv()

    kb_path = "menu_kb.md"
    if not os.path.exists(kb_path):
        raise FileNotFoundError(f"Knowledge base file '{kb_path}' not found.")

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

    # Encode query ด้วย embed_fn (Google text-embedding-004)
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
        "คุณคือ AI Assistant ประจำร้าน EasyMart\n"
        "ให้ตอบคำถามของลูกค้าโดยใช้ข้อมูลใน Context ต่อไปนี้เท่านั้น\n"
        "ตอบอย่างสุภาพ กระชับ เป็นกันเอง และถูกต้องตามข้อมูลใน Context\n"
        "หากใน Context ไม่มีข้อมูลที่ใช้ตอบคำถาม ให้ตอบว่าไม่ทราบข้อมูลหรือไม่พบข้อมูลในระบบ\n\n"
        f"Context:\n{context_text}\n\n"
        f"คำถาม: {query}\n"
        "คำตอบ:"
    )

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        answer = response.text.strip() if response.text else "ไม่มีคำตอบจากระบบ"
    except Exception as exc:
        answer = f"เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gemini: {exc}"

    duration_ms = (time.time() - start_time) * 1000
    if trace_id:
        log_span(
            trace_id=trace_id,
            span_name="generate_answer",
            duration_ms=duration_ms,
            inputs={"query": query, "model": model_name, "context_count": len(context_chunks)},
            outputs={"answer": answer},
        )

    return answer


def main():
    st.set_page_config(page_title="EasyMart RAG Chatbot", page_icon="🛒")
    st.title("EasyMart RAG Chatbot 🛒")
    st.caption("ถามอะไรเกี่ยวกับ EasyMart ได้เลย ตอบจากข้อมูลร้านของเรา")

    try:
        embed_fn, index, chunks = load_index()
    except NotImplementedError as exc:
        st.error(f"TODO not implemented: {exc}")
        st.stop()
    except Exception as exc:
        st.error(f"เกิดข้อผิดพลาดในการโหลด Index: {exc}")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("ถามอะไรเกี่ยวกับ EasyMart"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("กำลังค้นข้อมูล..."):
                trace_id = str(uuid.uuid4())
                start_retrieve = time.time()
                context = retrieve_top_k(prompt, embed_fn, index, chunks, k=3, trace_id=trace_id)
                retrieve_time = (time.time() - start_retrieve) * 1000

                start_gen = time.time()
                answer = generate_answer(prompt, context, trace_id=trace_id)
                gen_time = (time.time() - start_gen) * 1000

            st.write(answer)

            with st.expander("Source chunks"):
                for i, c in enumerate(context, 1):
                    st.markdown(f"**[{i}]** {c}")

            with st.expander("Trace (Observability)"):
                st.json({
                    "trace_id": trace_id,
                    "retrieval_ms": round(retrieve_time, 2),
                    "generation_ms": round(gen_time, 2),
                    "total_ms": round(retrieve_time + gen_time, 2),
                    "top_k_chunks_retrieved": len(context),
                })

        st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
