from langchain_ollama import ChatOllama
from langchain_community.utilities import SQLDatabase
from langchain.chains import create_sql_query_chain
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from app.db.connection import DB_PATH

SYSTEM_PROMPT = """You are an assistant that answers questions about vehicle listings.
You have access to a SQLite database with a 'listings' table.

The table has these columns:
- id: unique listing ID
- title: vehicle description (e.g. "2023 Mazda CX-5, 2.5L, all wheel drive")
- price: integer price in the currency specified
- currency: price currency (e.g. "USD")
- details: location, year, mileage, fuel type (e.g. "Kentron, 2023 y., 56,000 km, Gasoline")
- is_dealer: 1 if dealer listing, 0 if private
- url: link to the listing

Rules:
- Only generate SELECT queries. Never modify data.
- Always add LIMIT 20 unless the user asks for a count or aggregate.
- The 'details' column contains comma-separated info: location, year, mileage, fuel type.
  Use LIKE for filtering on these (e.g. details LIKE '%Gasoline%').
- The 'title' column contains the vehicle make, model, engine size.
  Use LIKE for filtering (e.g. title LIKE '%CX-5%').
"""

ANSWER_PROMPT = ChatPromptTemplate.from_template(
    """Given this user question, SQL query, and SQL result, write a clear answer.
Keep it concise. If there are listings, mention key details (title, price, location).

Question: {question}
SQL Query: {query}
SQL Result: {result}

Answer:"""
)


def _create_db():
    return SQLDatabase.from_uri(
        f"sqlite:///{DB_PATH}",
        include_tables=["listings"],
        sample_rows_in_table_info=3,
    )


def _clean_sql(raw: str) -> str:
    """Extract just the SQL query from LLM output."""
    import re

    # Remove markdown code fences if present
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()

    # Find the SELECT ... ; statement (may span multiple lines)
    select_match = re.search(r"(SELECT\b.*)", raw, re.DOTALL | re.IGNORECASE)
    if select_match:
        sql = select_match.group(1).strip()
        # Cut off anything after the first semicolon or after a blank line of prose
        semi = sql.find(";")
        if semi != -1:
            sql = sql[:semi + 1]
        return sql

    return raw.strip()


def run_cli():
    """Interactive CLI: ask questions about listings in natural language."""
    db = _create_db()
    llm = ChatOllama(model="llama3", temperature=0)

    sql_chain = create_sql_query_chain(llm, db)
    answer_llm = ChatOllama(model="llama3", temperature=0)

    print("ListAM Vehicle Search (type 'quit' to exit)")
    print("=" * 50)

    while True:
        try:
            question = input("\nAsk: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not question or question.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        try:
            # Step 1: Generate SQL
            raw_sql = sql_chain.invoke({"question": question})
            sql = _clean_sql(raw_sql)
            print(f"\n  SQL: {sql}")

            # Step 2: Execute SQL
            result = db.run(sql)
            print(f"  Result: {result[:500]}")

            # Step 3: Generate human answer
            answer = answer_llm.invoke(
                ANSWER_PROMPT.format(question=question, query=sql, result=result)
            )
            print(f"\n  {answer.content}")

        except Exception as e:
            print(f"\n  Error: {e}")
