#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
source backend/.venv/bin/activate
python -m compileall -q backend/app
python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from app.main import app
from app.storage import chunks, documents
from app.retrieval import hybrid_retrieve
from app.graph import rebuild_graph

cs = chunks()
article21 = [c for c in cs if c.get('article') == '21']
assert len(article21) >= 1, f'Expected at least 1 Article 21 chunk, found {len(article21)}'
substantive21 = [c for c in article21 if 'Protection of life' in c.get('text', '') or c.get('page') in (48, 74)]
assert len(substantive21) >= 1, f'Substantive Article 21 (Protection of life) not found in {article21}'
assert substantive21[0].get('chunk_type') in ('article', 'constitutional_article'), substantive21[0]

r = hybrid_retrieve(cs, rebuild_graph(), 'What does Article 21 of the Constitution of India provide?', top_k=5, strategy={'dense_weight':0.2,'lexical_weight':0.6,'graph_weight':0.2})
fused = r['fused']
assert fused, 'No retrieval results'
assert fused[0]['chunk'].get('article') == '21', fused[0]
assert 'Protection of life' in fused[0]['chunk'].get('text', '') or fused[0]['chunk'].get('page') in (48, 74), fused[0]

print('Backend import: OK')
print('Routes:', len(app.routes))
print('Documents:', len(documents()))
print('Chunks:', len(cs))
print(f'Article 21: OK (page {substantive21[0].get("page")}, substantive fundamental right chunk)')
print('Article 21 retrieval: OK')
PY
echo "PROJECT CHECK: PASS"
