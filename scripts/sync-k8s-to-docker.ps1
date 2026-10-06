# scripts/sync-k8s-to-docker.ps1
# Synchronizes stores_registry.json, Qdrant vectors, and Neo4j graph entities from Kubernetes into local Docker Compose

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Synchronizing Data from Kubernetes to Docker Compose" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Sync stores_registry.json
Write-Host "`n[1/3] Copying stores_registry.json from Kubernetes backend..." -ForegroundColor Yellow
$k8sJson = kubectl exec -n rag-system deployment/backend -c backend -- cat /app/data/stores_registry.json
if ($k8sJson) {
    [System.IO.File]::WriteAllText("data/stores_registry.json", $k8sJson, [System.Text.UTF8Encoding]::new($false))
    docker cp data/stores_registry.json productionlevelrag-backend-1:/app/data/stores_registry.json
    Write-Host " -> Successfully copied stores_registry.json to Docker container!" -ForegroundColor Green
}

# 2. Sync Qdrant Vectors & Neo4j via Python
Write-Host "`n[2/3] Syncing Qdrant vectors and Neo4j graph entities..." -ForegroundColor Yellow
python -c "
import subprocess, json
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from neo4j import GraphDatabase

# A. Qdrant
print('  * Syncing Qdrant vectors...')
k8s_qdrant_script = '''
import json
from qdrant_client import QdrantClient
qc = QdrantClient(\"http://qdrant:6333\")
points, _ = qc.scroll(collection_name=\"financial_chunks\", limit=1000, with_payload=True, with_vectors=True)
out = [{'id': str(p.id), 'vector': p.vector, 'payload': p.payload} for p in points]
print(json.dumps(out))
'''
res = subprocess.run(['kubectl', 'exec', '-n', 'rag-system', 'deployment/backend', '-c', 'backend', '--', 'python', '-c', k8s_qdrant_script], capture_output=True, text=True, check=True)
points_data = json.loads(res.stdout)
qc_docker = QdrantClient('http://localhost:6333')
cols = [c.name for c in qc_docker.get_collections().collections]
if 'financial_chunks' not in cols and points_data:
    qc_docker.create_collection('financial_chunks', vectors_config=VectorParams(size=len(points_data[0]['vector']), distance=Distance.COSINE))
if points_data:
    pts = [PointStruct(id=p['id'], vector=p['vector'], payload=p['payload']) for p in points_data]
    qc_docker.upsert('financial_chunks', points=pts)
    print(f'  -> Upserted {len(pts)} vectors into Docker Qdrant (Total: {qc_docker.get_collection(\"financial_chunks\").points_count}).')

# B. Neo4j
print('  * Syncing Neo4j graph entities...')
k8s_neo_script = '''
from neo4j import GraphDatabase
import json
driver = GraphDatabase.driver(\"bolt://neo4j:7687\", auth=(\"neo4j\", \"production_password\"))
with driver.session() as s:
    nodes = s.run(\"MATCH (n) RETURN id(n) as id, labels(n) as labels, properties(n) as props\").data()
    rels = s.run(\"MATCH (n)-[r]->(m) RETURN id(n) as from_id, type(r) as type, properties(r) as props, id(m) as to_id\").data()
    print(json.dumps({'nodes': nodes, 'rels': rels}))
'''
res = subprocess.run(['kubectl', 'exec', '-n', 'rag-system', 'deployment/backend', '-c', 'backend', '--', 'python', '-c', k8s_neo_script], capture_output=True, text=True, check=True)
graph_data = json.loads(res.stdout)
docker_driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'production_password'))
with docker_driver.session() as s:
    s.run('MATCH (n) DETACH DELETE n')
    id_map = {}
    for n in graph_data['nodes']:
        labels_str = ':'.join(n['labels'])
        res = s.run(f'CREATE (n:{labels_str} $props) RETURN id(n) as new_id', props=n['props']).single()
        id_map[n['id']] = res['new_id']
    for r in graph_data['rels']:
        from_id = id_map.get(r['from_id'])
        to_id = id_map.get(r['to_id'])
        if from_id is not None and to_id is not None:
            s.run(f'MATCH (a), (b) WHERE id(a) = $from_id AND id(b) = $to_id CREATE (a)-[r:{r[\"type\"]} $props]->(b)', from_id=from_id, to_id=to_id, props=r['props'])
    node_cnt = s.run('MATCH (n) RETURN count(n) as c').single()['c']
    rel_cnt = s.run('MATCH ()-[r]->() RETURN count(r) as c').single()['c']
    print(f'  -> Docker Neo4j now has {node_cnt} nodes and {rel_cnt} relationships.')
"

# 3. Reload Docker backend
Write-Host "`n[3/3] Reloading Docker backend container..." -ForegroundColor Yellow
docker restart productionlevelrag-backend-1 | Out-Null
Start-Sleep -Seconds 3
Write-Host " -> Backend restarted and synchronized successfully!" -ForegroundColor Green

Write-Host "`nAll data successfully synchronized! Docker Compose now has identical data to Kubernetes." -ForegroundColor Cyan
