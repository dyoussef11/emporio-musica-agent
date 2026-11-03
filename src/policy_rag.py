"""
RAG leve sobre o manual de políticas (PDF) usando TF-IDF.

Decisões:
- TF-IDF local em vez de embeddings: PDF de 8 páginas, protótipo, zero custo.
- Chunking por parágrafo com merge até MAX_CHUNK_CHARS: preserva cláusulas
  completas (ex.: prazo + condições + exceção de devolução ficam juntos).
- Remoção do cabeçalho repetido em toda página ("Empório da Música Manual
  de Políticas e Procedimentos") antes do fit do TF-IDF: evita que o
  cabeçalho domine os scores e empurre a seção correta para baixo.
- sublinear_tf=True: amortece termos que aparecem muitas vezes no mesmo
  chunk, dando mais peso a termos raros e específicos.
- Chunk carrega a página de origem: permite ao LLM citar a fonte.
- MIN_SCORE: corta ruído; se nada passar, a ferramenta retorna vazio com
  aviso em vez de devolver trechos irrelevantes.
- Índice é cacheado com @lru_cache(maxsize=1) — o PDF não muda em runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src import config

MIN_CHUNK_CHARS = 80
MAX_CHUNK_CHARS = 600
MIN_SCORE = 0.03


# --------------------------------------------------------------------- #
# Regex de saneamento
# --------------------------------------------------------------------- #
# Remove caracteres de controle e private-use que o PDF gera em tabelas
# (por exemplo a tabela de frete na página 5). Mantém ASCII imprimível,
# Latin-1 Supplement, Latin Extended-A e pontuação geral/unicode.
_PRIVATE_USE_OR_CONTROL = re.compile(
    r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F\u2000-\u206F]"
)

# Cabeçalho que aparece em toda página — remove antes do fit.
_RUNNING_HEADER = re.compile(
    r"Emp[oó]rio\s+da\s+M[uú]sica\s+Manual\s+de\s+Pol[ií]ticas\s+e\s+Procedimentos",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chunk:
    page: int
    text: str


class PolicyIndex:
    """Índice TF-IDF sobre os chunks do manual de políticas."""

    def __init__(self, pdf_path: Path) -> None:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF de políticas não encontrado: {pdf_path}")

        self.chunks: list[Chunk] = _load_and_chunk(pdf_path)
        if not self.chunks:
            raise RuntimeError(
                "Não foi possível extrair texto do PDF de políticas. "
                "Verifique se o arquivo está íntegro."
            )

        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
            token_pattern=r"(?u)\b\w+\b",
        )
        self.matrix = self.vectorizer.fit_transform([c.text for c in self.chunks])

    def search(self, query: str, top_k: int = 4) -> list[tuple[Chunk, float]]:
        if not query or not query.strip():
            return []
        q_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self.matrix).ravel()
        top_idx = scores.argsort()[::-1][:top_k]
        return [
            (self.chunks[int(i)], float(scores[int(i)]))
            for i in top_idx
            if scores[int(i)] >= MIN_SCORE
        ]


# --------------------------------------------------------------------- #
# Load + chunk
# --------------------------------------------------------------------- #
def _load_and_chunk(pdf_path: Path) -> list[Chunk]:
    reader = PdfReader(str(pdf_path))
    chunks: list[Chunk] = []
    for page_num, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        cleaned = _clean_text(raw)
        for chunk_text in _split_into_chunks(cleaned):
            stripped = _strip_header(chunk_text)
            if len(stripped) >= MIN_CHUNK_CHARS:
                chunks.append(Chunk(page=page_num, text=stripped))
    return chunks


def _clean_text(text: str) -> str:
    """Remove caracteres problemáticos, normaliza espaços unicode e quebras."""
    text = _PRIVATE_USE_OR_CONTROL.sub(" ", text)
    # Normaliza espaços unicode (NBSP, narrow NBSP, etc.) para espaço comum
    text = (
        text.replace("\u00A0", " ")
        .replace("\u202F", " ")
        .replace("\u2007", " ")
    )
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_header(text: str) -> str:
    """Remove o cabeçalho repetido em toda página ('Empório da Música Manual...')."""
    return _RUNNING_HEADER.sub("", text).strip()


def _split_into_chunks(text: str) -> list[str]:
    """Quebra por parágrafos e junta até MAX_CHUNK_CHARS."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= MAX_CHUNK_CHARS:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


# --------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_policy_index() -> PolicyIndex:
    return PolicyIndex(config.POLICIES_PDF)