# Neo4j Cypher Query Catalog & Reference Guide

This document is a comprehensive reference for all Neo4j Cypher queries used across the **Production-level Financial RAG System**, including:
1. **Connection Details & Access Methods**
2. **Graph Schema & Data Model**
3. **Internal Application Queries** (Indexing, Retrieval, Router, MCP Tools, Healthcheck)
4. **Interactive Inspection & Diagnostic Queries** (Ready-to-run in Neo4j Browser)
5. **Database Maintenance & Cleanup Queries**

---

## 1. Connection Details & Access

### Web Browser Interface
- **URL**: [http://localhost:7474](http://localhost:7474)
- **Authentication**:
  - **Username**: `neo4j`
  - **Password**: `production_password` (or value of `NEO4J_PASSWORD` in `.env`)
  - **Connect URL / Host**: `bolt://localhost:7687`

### Command-Line (Docker Cypher-Shell)
Execute Cypher queries directly through the container terminal:
```powershell
docker compose exec neo4j cypher-shell -u neo4j -p production_password
```

Or pass a query directly:
```powershell
docker compose exec neo4j cypher-shell -u neo4j -p production_password "MATCH (n) RETURN count(n) AS total_nodes;"
```

### Python Driver Connection Settings
- **URI**: `bolt://neo4j:7687` (internal container) / `bolt://localhost:7687` (host machine)
- **Database**: `neo4j` (default)

---

## 2. Graph Schema & Data Model

The graph accommodates both **unstructured narrative chunks** and **structured tabular metrics** scoped by tenant/store:

```mermaid
graph TD
    Store["(:Store {id, name})"]
    Doc["(:Document {id, filename, store_id})"]
    Metric["(:Metric {id, name, store_id, category})"]
    FinEntity["(:FinancialEntity {name, category})"]
    Period["(:Period / :Quarter {id, name, store_id})"]

    Store -->|HAS_DOCUMENT| Doc
    Store -->|CONTAINS| Metric
    Store -->|CONTAINS| FinEntity
    Doc -->|DEFINES| Metric
    Doc -->|REPORTED_METRIC| Metric
    Doc -->|MENTIONS| FinEntity
    Metric -->|HAS_VALUE {value, doc_id, store_id}| Period
    FinEntity -->|RELATED {type}| FinEntity
```

### Node Labels
| Label | Description | Key Properties |
|---|---|---|
| `:Store` | High-level data store / tenant container | `id`, `name` |
| `:Document` | Source file ingested into the store | `id`, `filename`, `store_id` |
| `:FinancialEntity` | Extracted financial concepts/line items | `name`, `category` |
| `:Metric` | Extracted numerical or tabular metric | `id`, `name`, `store_id`, `category` |
| `:Period` / `:Quarter`| Temporal targets (e.g. `Q1 2024`, `FY23`) | `id`, `name`, `store_id` |

### Relationship Types
| Relationship | Start Node &rarr; End Node | Properties | Description |
|---|---|---|---|
| `[:HAS_DOCUMENT]` | `(:Store)` &rarr; `(:Document)` | none | Links a document to its store |
| `[:CONTAINS]` | `(:Store)` &rarr; `(:Metric)` or `(:FinancialEntity)` | none | Scopes entities to a store |
| `[:DEFINES]` | `(:Document)` &rarr; `(:Metric)` | none | Provenance link from document |
| `[:REPORTED_METRIC]` | `(:FinancialEntity)` &rarr; `(:Metric)` | `chunk_id`, `content`, `source_file` | Provenance to raw text chunk |
| `[:REPORTED_VALUE]` | `(:Metric)` &rarr; `(:Period)` or `(:Date)` | `value`, `doc_id`, `store_id`, `source_file` | Numerical value recorded for a period |
| `[:HAS_VALUE]` | `(:Metric)` &rarr; `(:Period)` or `(:Quarter)` | `value`, `doc_id`, `store_id`, `source_file`, `chunk_id` | Stores financial number for a period |
| `[:MENTIONS]` | `(:FinancialEntity)` &rarr; `(:Metric)` | `chunk_id`, `content`, `source_file` | Unstructured text mentions |
| `[:RELATED]` | `(:FinancialEntity)` &rarr; `(:FinancialEntity)` | `type`, and dynamic metadata | Cross-entity relationship |

---

## 3. Internal Application Queries

Below are all Cypher queries executed programmatically by the backend code.

### 3.1. Entity Upsert (GraphStore)
- **Source**: [`src/indexing/graph_store.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/indexing/graph_store.py#L24-L28)
- **Purpose**: Upserts an extracted financial entity from text/markdown chunks.
```cypher
MERGE (node:FinancialEntity {name: $name, category: $category})
```
*Parameters*:
- `$name` (str): Entity name (e.g., `"Revenue"`, `"Operating Expenses"`)
- `$category` (str): Classification (e.g., `"Metric"`, `"Document"`, `"Quarter"`)

---

### 3.2. Relationship Upsert (GraphStore)
- **Source**: [`src/indexing/graph_store.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/indexing/graph_store.py#L30-L39)
- **Purpose**: Creates or updates a directed edge between two entities with properties.
```cypher
MATCH (source:FinancialEntity {name: $source})
MATCH (target:FinancialEntity {name: $target})
MERGE (source)-[edge:RELATED {type: $relationship_type}]->(target)
SET edge += $properties
```
*Parameters*:
- `$source` (str): Source entity name
- `$target` (str): Target entity name
- `$relationship_type` (str): Edge label (e.g., `"REPORTED_METRIC"`, `"HAS_VALUE"`, `"MENTIONS"`)
- `$properties` (map): Metadata including `chunk_id`, `content`, `source_file`, `value`

---

### 3.3. Tabular Ingestion: Store & Document Root Setup
- **Source**: [`src/ingestion/parsers/tabular_pipeline.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/ingestion/parsers/tabular_pipeline.py#L191-L197)
- **Purpose**: Sets up root Store and Document nodes when uploading CSV/XLSX.
```cypher
MERGE (s:Store {id: $store_id})
ON CREATE SET s.name = $store_name
MERGE (d:Document {id: $doc_id})
ON CREATE SET d.filename = $filename, d.store_id = $store_id
MERGE (s)-[:HAS_DOCUMENT]->(d)
```
*Parameters*:
- `$store_id` (str): Store UUID / identifier
- `$store_name` (str): Display name of store
- `$doc_id` (str): Unique document ID
- `$filename` (str): Name of uploaded file

---

### 3.4. Tabular Ingestion: Batch Entity Ingestion
- **Source**: [`src/ingestion/parsers/tabular_pipeline.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/ingestion/parsers/tabular_pipeline.py#L202-L215)
- **Purpose**: Unwinds table rows, merges entities with store-scoped composite IDs, and links them to Store and Document.
```cypher
UNWIND $rows AS row
WITH row WHERE row['{key_col}'] IS NOT NULL AND toString(row['{key_col}']) <> ''
MERGE (e:{entity_label} {id: $store_id + '#' + toString(row['{key_col}'])})
SET e.name = toString(row['{key_col}']),
    e.store_id = $store_id,
    e.category = '{entity_label}'
WITH e
MATCH (s:Store {id: $store_id})
MATCH (d:Document {id: $doc_id})
MERGE (s)-[:CONTAINS]->(e)
MERGE (d)-[:DEFINES]->(e)
```
*Format values*:
- `{key_col}`: Column name for entity (e.g. `"Metric"`, `"Line Item"`)
- `{entity_label}`: Entity label (defaults to `"Metric"`)
*Parameters*:
- `$rows` (list[dict]): Cleaned row data
- `$store_id` (str), `$doc_id` (str)

---

### 3.5. Tabular Ingestion: Metric Temporal Edges
- **Source**: [`src/ingestion/parsers/tabular_pipeline.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/ingestion/parsers/tabular_pipeline.py#L227-L237)
- **Purpose**: Creates temporal nodes (e.g., `Period`) and links metrics via `HAS_VALUE` with the exact numerical value.
```cypher
UNWIND $rows AS row
WITH row WHERE row['{key_col}'] IS NOT NULL AND row['{val_col}'] IS NOT NULL AND toString(row['{val_col}']) <> ''
MATCH (e:{entity_label} {id: $store_id + '#' + toString(row['{key_col}'])})
MERGE (t:{temporal_node} {id: $store_id + '#' + '{temporal_val}'})
SET t.name = '{temporal_val}', t.store_id = $store_id
MERGE (e)-[r:{edge_name} {doc_id: $doc_id, store_id: $store_id}]->(t)
SET r.value = toString(row['{val_col}']),
    r.source_file = $filename
```
*Format values*:
- `{val_col}`: Column name holding the value
- `{temporal_node}`: Label (defaults to `"Period"`)
- `{temporal_val}`: Period value (e.g. `"Q1 2024"`, `"2023"`)
- `{edge_name}`: Relationship type (defaults to `"HAS_VALUE"`)

---

### 3.6. Global Graph Retrieval (`GRAPH_QUERY`)
- **Source**: [`src/retrieval/graph_search.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/retrieval/graph_search.py#L12-L27)
- **Purpose**: Performs a 1-to-2 hop traversal across matching financial entities, scoring results by inverse path length (`1.0 / hops`).
```cypher
MATCH (entity:FinancialEntity)
WHERE toLower($query_text) CONTAINS toLower(entity.name)
MATCH path=(entity)-[*1..2]-(connected:FinancialEntity)
UNWIND relationships(path) AS relation
WITH entity, relation, connected, length(path) AS hops
WHERE relation.chunk_id IS NOT NULL
RETURN relation.chunk_id AS id,
       coalesce(relation.content, relation.value, connected.name) AS content,
       1.0 / hops AS score,
       {entity: entity.name, connected_entity: connected.name, hops: hops,
        graph_nodes_traversed: [entity.name, connected.name],
        source_file: relation.source_file} AS metadata
ORDER BY score DESC
LIMIT $limit
```
*Parameters*:
- `$query_text` (str): Search prompt from user
- `$limit` (int): Number of contexts to return

---

### 3.7. Store-Scoped Graph Retrieval (`STORE_SCOPED_GRAPH_QUERY`)
- **Source**: [`src/retrieval/graph_search.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/retrieval/graph_search.py#L29-L48)
- **Purpose**: Store-isolated multi-hop graph traversal for specific store / workspace tenants.
```cypher
MATCH (entity)
WHERE (entity:FinancialEntity OR entity:Metric)
  AND (entity.store_id = $store_id OR ($store_id = 'default' AND entity.store_id IS NULL))
  AND toLower($query_text) CONTAINS toLower(entity.name)
MATCH path=(entity)-[*1..2]-(connected)
WHERE (connected.store_id = $store_id OR ($store_id = 'default' AND connected.store_id IS NULL))
UNWIND relationships(path) AS relation
WITH entity, relation, connected, length(path) AS hops
WHERE (relation.store_id = $store_id OR ($store_id = 'default' AND relation.store_id IS NULL))
RETURN coalesce(relation.chunk_id, entity.id, toString(id(entity))) AS id,
       coalesce(relation.content, relation.value, connected.name, entity.name) AS content,
       1.0 / hops AS score,
       {entity: entity.name, connected_entity: connected.name, hops: hops,
        graph_nodes_traversed: [entity.name, connected.name],
        source_file: relation.source_file,
        store_id: $store_id} AS metadata
ORDER BY score DESC
LIMIT $limit
```
*Parameters*:
- `$store_id` (str): Target store ID
- `$query_text` (str): Search prompt
- `$limit` (int): Maximum contexts

---

### 3.8. Router Store Traversal (`generate_store_cypher`)
- **Source**: [`src/retrieval/router.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/retrieval/router.py#L71-L78)
- **Purpose**: Generates bounded 1-hop traversal for queries classified under `GRAPH_TRAVERSAL` route.
```cypher
MATCH (s:Store {id: $store_id})-[:CONTAINS]->(e)
WHERE ($keyword = '' OR toLower(e.name) CONTAINS toLower($keyword))
OPTIONAL MATCH (e)-[r]->(t)
WHERE r.store_id = $store_id OR r.store_id IS NULL
RETURN e.name AS entity, type(r) AS relationship, t.name AS target, r.value AS value
LIMIT 25
```
*Parameters*:
- `$store_id` (str): Target store
- `$keyword` (str): Extracted keyword from query

---

### 3.9. MCP Tool: Graph Entity Inspection
- **Source**: [`src/mcp/tools.py`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/mcp/tools.py#L105-L116)
- **Purpose**: Inspects a specific financial entity and aggregates all incoming and outgoing relations for AI tools.
```cypher
MATCH (entity:FinancialEntity {name: $entity_name})
OPTIONAL MATCH (entity)-[relation]-(connected:FinancialEntity)
RETURN entity.name AS entity_name,
       entity.category AS category,
       collect({
           type: type(relation),
           direction: CASE WHEN startNode(relation) = entity THEN 'outgoing' ELSE 'incoming' END,
           connected_entity: connected.name,
           properties: properties(relation)
       }) AS relations
```
*Parameters*:
- `$entity_name` (str): Target entity name (e.g. `"Revenue"`)

---

### 3.10. Health Check Probe
- **Source**: [`docker-compose.yml:141`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/docker-compose.yml#L141) & [`src/observability.py:137`](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/src/observability.py#L137)
- **Purpose**: Liveness and readiness probe for Docker Compose and Prometheus health endpoints.
```cypher
RETURN 1
```

---

## 4. Interactive Inspection Queries (Run in Neo4j Browser)

Open [http://localhost:7474](http://localhost:7474) and paste any of these queries:

### 4.1. Visual Schema Overview
View the visual schema graph of all node labels and relationships:
```cypher
CALL db.schema.visualization()
```

### 4.2. Database Statistics (Node & Relationship Counts)
Get a quick count of all node labels and relationship types:
```cypher
CALL {
  MATCH (n)
  RETURN labels(n) AS labels, count(n) AS count, "Node" AS kind
}
UNION
CALL {
  MATCH ()-[r]->()
  RETURN [type(r)] AS labels, count(r) AS count, "Relationship" AS kind
}
RETURN kind, labels, count
ORDER BY kind, count DESC;
```

### 4.3. View Stores & Associated Documents
Inspect all registered stores and their indexed documents:
```cypher
MATCH (s:Store)-[r:HAS_DOCUMENT]->(d:Document)
RETURN s.id AS store_id, s.name AS store_name, d.id AS doc_id, d.filename AS filename
ORDER BY store_name, filename;
```

### 4.4. View Metric Values by Period (Financial Table Inspection)
View structured metrics and their reported values per period/quarter:
```cypher
MATCH (m:Metric)-[r:HAS_VALUE]->(p)
RETURN m.name AS metric,
       r.value AS value,
       p.name AS period,
       r.source_file AS source_file,
       r.store_id AS store_id
ORDER BY metric, period
LIMIT 50;
```

### 4.5. Explore Knowledge Graph Subgraph (Graph Visualizer)
Retrieve a visual graph sample of 50 connected nodes and edges:
```cypher
MATCH (a)-[r]->(b)
RETURN a, r, b
LIMIT 50;
```

### 4.6. Search for an Entity by Name (Case-Insensitive)
Find any entity whose name contains a search term:
```cypher
MATCH (e)
WHERE (e:FinancialEntity OR e:Metric)
  AND toLower(e.name) CONTAINS toLower('revenue')
OPTIONAL MATCH (e)-[r]-(connected)
RETURN e, r, connected
LIMIT 25;
```

### 4.7. Find Multi-Hop Relationships (e.g., Metric &rarr; Quarter &rarr; Other Metric)
Discover connected financial concepts within 2 hops:
```cypher
MATCH path = (e:Metric {name: 'Revenue'})-[*1..2]-(other)
RETURN path
LIMIT 20;
```

### 4.8. Inspect All Values for a Specific Document
Find every metric and relationship generated from a given document filename:
```cypher
MATCH (d:Document {filename: 'sample_financials.csv'})-[:DEFINES]->(m:Metric)-[r:HAS_VALUE]->(p)
RETURN m.name AS metric, r.value AS value, p.name AS period
ORDER BY metric;
```

### 4.9. Find Isolated (Orphan) Nodes
Find nodes that have no relationships (useful for indexing debugging):
```cypher
MATCH (n)
WHERE NOT (n)--()
RETURN labels(n) AS label, count(n) AS orphan_count, collect(n.name)[0..5] AS sample_names;
```

---

## 5. Maintenance & Cleanup Queries

> [!WARNING]
> Run write/delete queries carefully. Deleting nodes will remove relationships linked to them.

### 5.1. Delete Data for a Specific Store Only
Delete all entities, documents, and relationships belonging to a single store without affecting other stores:
```cypher
// Step 1: Remove relationships and metrics for a specific store
MATCH (s:Store {id: 'default'})-[:CONTAINS]->(e)
DETACH DELETE e;

// Step 2: Remove documents for that store
MATCH (s:Store {id: 'default'})-[:HAS_DOCUMENT]->(d:Document)
DETACH DELETE d;

// Step 3: Remove the store node itself
MATCH (s:Store {id: 'default'})
DETACH DELETE s;
```

### 5.2. Delete Orphan / Disconnected Nodes
Clean up leftover nodes that have lost their edges:
```cypher
MATCH (n)
WHERE NOT (n)--()
DELETE n;
```

### 5.3. Reset Entire Graph Database (Complete Wipe)
Delete everything in the Neo4j instance:
```cypher
MATCH (n)
DETACH DELETE n;
```
