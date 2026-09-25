"""Batch lexical matching, with no trained model or opaque weights."""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .skills import clean_skills, find_evidence, normalize

ALGORITHM = 'skills-first-tfidf-v1'


def tokens(text):
    # Preserve technical tokens such as C++, C#, node.js and CI/CD.
    return re.findall(r'\w+(?:[+#]+|(?:[./-]\w+)*)', normalize(text))


def score_batch(description, required_skills, texts):
    if not texts:
        return []
    required = clean_skills(required_skills)
    corpus = [description] + list(texts)
    vectorizer = TfidfVectorizer(tokenizer=tokens, token_pattern=None,
                               lowercase=False, sublinear_tf=True, max_features=30000)
    try:
        vectors = vectorizer.fit_transform(corpus)
        similarities = cosine_similarity(vectors[1:], vectors[0]).ravel()
    except ValueError as exc:
        if 'empty vocabulary' not in str(exc):
            raise
        similarities = [0.0] * len(texts)
    results = []
    for text, similarity in zip(texts, similarities):
        evidence = {s: find_evidence(text, s) for s in required}
        matched = [s for s in required if evidence[s]]
        missing = [s for s in required if not evidence[s]]
        skills_score = 100.0 * len(matched) / len(required) if required else None
        cosine_score = min(100.0, max(0.0, float(similarity) * 100.0))
        results.append(dict(overall_score=skills_score if required else cosine_score,
                            cosine_score=cosine_score, skills_score=skills_score,
                            matching_skills=matched, missing_skills=missing,
                            evidence={s: evidence[s] for s in matched}, algorithm=ALGORITHM))
    return results
