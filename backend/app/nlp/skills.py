"""Explicit, editable vocabulary. A mention is evidence, not proof of proficiency."""
import re
import unicodedata

ALIASES = {
    'Python': ['python'], 'FastAPI': ['fastapi', 'fast api'],
    'PostgreSQL': ['postgresql', 'postgres'], 'Docker': ['docker'],
    'Git': ['git'], 'AWS': ['aws', 'amazon web services'],
    'Kubernetes': ['kubernetes', 'k8s'], 'Java': ['java'],
    'JavaScript': ['javascript', 'js'], 'TypeScript': ['typescript', 'ts'],
    'React': ['react', 'react.js', 'reactjs'], 'Node.js': ['node.js', 'nodejs'],
    'SQL': ['sql'], 'MySQL': ['mysql'], 'SQLite': ['sqlite'],
    'MongoDB': ['mongodb', 'mongo'], 'Redis': ['redis'],
    'Django': ['django'], 'Flask': ['flask'], 'SQLAlchemy': ['sqlalchemy'],
    'Linux': ['linux'], 'Bash': ['bash'], 'C++': ['c++'], 'C#': ['c#'],
    '.NET': ['.net', 'dotnet'], 'Go': ['go', 'golang'], 'Rust': ['rust'],
    'HTML': ['html', 'html5'], 'CSS': ['css', 'css3'],
    'Terraform': ['terraform'], 'Azure': ['azure'], 'GCP': ['gcp', 'google cloud'],
    'CI/CD': ['ci/cd', 'ci cd'], 'REST': ['rest', 'restful'],
    'GraphQL': ['graphql'], 'Pytest': ['pytest'], 'Pandas': ['pandas'],
    'NumPy': ['numpy'], 'scikit-learn': ['scikit-learn', 'sklearn'],
    'TensorFlow': ['tensorflow'], 'PyTorch': ['pytorch'],
    'Excel': ['excel'], 'Power BI': ['power bi', 'powerbi'],
    'Spring': ['spring', 'spring boot'], 'RabbitMQ': ['rabbitmq'], 'Kafka': ['kafka'],
}


def normalize(text):
    return unicodedata.normalize('NFKC', text).casefold()


def canonical(skill):
    value = normalize(skill.strip())
    for name, aliases in ALIASES.items():
        if value in [normalize(name)] + aliases:
            return name
    return skill.strip()


def clean_skills(skills):
    result = []
    seen = set()
    for skill in skills:
        name = canonical(skill)
        if name and normalize(name) not in seen:
            seen.add(normalize(name))
            result.append(name)
    return result


def find_evidence(text, skill):
    name = canonical(skill)
    aliases = ALIASES.get(name, [name])
    # Avoid treating Java as JavaScript, Git as GitHub, or C++ as C.
    pattern = r'(?<![\w+#])(?:' + '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r')(?![\w+#])'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return text[max(0, match.start()-60):min(len(text), match.end()+100)].strip()


def extract_skills(text):
    return [skill for skill in ALIASES if find_evidence(text, skill)]
