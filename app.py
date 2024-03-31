import os
import streamlit as st

from token_stream_handler import StreamHandler
from chat_profile import User, Assistant, ChatProfileRoleEnum

from langchain.chains import ConversationalRetrievalChain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_community.vectorstores.chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

__import__("pysqlite3")
import sys

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

st.set_page_config(page_title="InkChatGPT", page_icon="📚")


def load_and_process_file(file_data):
    """
    Load and process the uploaded file.
    Returns a vector store containing the embedded chunks of the file.
    """
    file_name = os.path.join("./", file_data.name)
    with open(file_name, "wb") as f:
        f.write(file_data.getvalue())

    _, extension = os.path.splitext(file_name)

    # Load the file using the appropriate loader
    if extension == ".pdf":
        loader = PyPDFLoader(file_name)
    elif extension == ".docx":
        loader = Docx2txtLoader(file_name)
    elif extension == ".txt":
        loader = TextLoader(file_name)
    else:
        st.error("This document format is not supported!")
        return None

    documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = text_splitter.split_documents(documents)
    embeddings = OpenAIEmbeddings(openai_api_key=st.secrets.OPENAI_API_KEY)
    vector_store = Chroma.from_documents(chunks, embeddings)
    return vector_store


def initialize_chat_model(vector_store):
    """
    Initialize the chat model with the given vector store.
    Returns a ConversationalRetrievalChain instance.
    """
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0,
        openai_api_key=st.secrets.OPENAI_API_KEY,
    )
    retriever = vector_store.as_retriever()
    return ConversationalRetrievalChain.from_llm(llm, retriever)


def main():
    """
    The main function that runs the Streamlit app.
    """

    if st.secrets.OPENAI_API_KEY:
        openai_api_key = st.secrets.OPENAI_API_KEY
    else:
        openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password")
        st.secrets.OPENAI_API_KEY = openai_api_key

        if not st.secrets.OPENAI_API_KEY:
            st.info("Please add your OpenAI API key to continue.")

    assistant_message = "Hello, you can upload a document and chat with me to ask questions related to its content. Start by adding OpenAI API Key in the sidebar."
    st.session_state["messages"] = [
        Assistant(message=assistant_message).build_message()
    ]

    st.chat_message(ChatProfileRoleEnum.Assistant).write(assistant_message)

    if prompt := st.chat_input(
        placeholder="Chat with your document",
        disabled=(not openai_api_key),
    ):
        st.session_state.messages.append(User(message=prompt).build_message())
        st.chat_message(ChatProfileRoleEnum.User).write(prompt)

        handle_question(prompt)


def handle_question(question):
    """
    Handles the user's question by generating a response and updating the chat history.
    """
    crc = st.session_state.crc

    if "history" not in st.session_state:
        st.session_state["history"] = []

    response = crc.run(
        {
            "question": question,
            "chat_history": st.session_state["history"],
        }
    )

    st.session_state["history"].append((question, response))

    for msg in st.session_state.messages:
        st.chat_message(msg.role).write(msg.content)

    with st.chat_message(ChatProfileRoleEnum.Assistant):
        stream_handler = StreamHandler(st.empty())
        llm = ChatOpenAI(
            openai_api_key=st.secrets.OPENAI_API_KEY,
            streaming=True,
            callbacks=[stream_handler],
        )
        response = llm.invoke(st.session_state.messages)
        st.session_state.messages.append(
            Assistant(message=response.content).build_message()
        )


def display_chat_history():
    """
    Displays the chat history in the Streamlit app.
    """

    if "history" in st.session_state:
        st.markdown("## Chat History")
        for q, a in st.session_state["history"]:
            st.markdown(f"**Question:** {q}")
            st.write(a)
            st.write("---")


def clear_history():
    """
    Clear the chat history stored in the session state.
    """
    if "history" in st.session_state:
        del st.session_state["history"]


def build_sidebar():
    with st.sidebar:
        st.title("📚 InkChatGPT")
        uploaded_file = st.file_uploader(
            "Select a file", type=["pdf", "docx", "txt"], key="file_uploader"
        )

        add_file = st.button(
            "Process File",
            disabled=(not uploaded_file and not st.secrets.OPENAI_API_KEY),
        )
        if add_file and uploaded_file and st.secrets.OPENAI_API_KEY.startswith("sk-"):
            with st.spinner("💭 Thinking..."):
                vector_store = load_and_process_file(uploaded_file)

                if vector_store:
                    crc = initialize_chat_model(vector_store)
                    st.session_state.crc = crc
                    st.chat_message(ChatProfileRoleEnum.Assistant).write(
                        f"File: `{uploaded_file.name}`, processed successfully!"
                    )


if __name__ == "__main__":
    build_sidebar()
    main()
