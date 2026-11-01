# FHIR R4 API Patterns Reference

Quick-reference for the tricky areas of FHIR R4 API design. All examples target FHIR R4 (v4.0.1).

---

## 1. Search Query Construction

### Search parameter types

| Type | Value syntax | Example |
|------|-------------|---------|
| token | `[system]\|[code]` or `[code]` | `code=http://loinc.org\|8480-6` |
| reference | `[type]/[id]` or `[id]` | `patient=Patient/123` |
| date | `[prefix]yyyy-MM-dd[THH:mm:ss[Z]]` | `date=ge2024-01-01&date=lt2025-01-01` |
| string | plain text (case/accent insensitive, start-match) | `name=peter` |
| quantity | `[prefix][number]\|[system]\|[code]` | `value-quantity=gt5.4\|http://unitsofmeasure.org\|mg` |
| uri | exact match by default | `url=http://example.org/fhir/ValueSet/123` |
| composite | two values joined with `$` | `component-code-value-quantity=http://loinc.org\|8480-6$lt60` |

### Modifiers

- `:exact` — case-sensitive full string match
- `:contains` — substring match
- `:missing=true/false` — presence/absence of a value
- `:not` — negation of token match (applies to the *set*, not individual entries)
- `:text` — search on display text of coded values
- `:in` / `:not-in` — membership in a ValueSet (requires terminology support)
- `:below` / `:above` — subsumption for tokens; hierarchical match for uri
- `:of-type` — match Identifier by type: `identifier:of-type=http://terminology.hl7.org/CodeSystem/v2-0203|MR|446053`
- `:identifier` — search Reference by identifier instead of literal reference

### Prefixes (date, number, quantity)

`eq` (default), `ne`, `gt`, `lt`, `ge`, `le`, `sa` (starts-after), `eb` (ends-before), `ap` (approximately)

### AND vs OR

- AND: repeat the parameter — `language=FR&language=NL` → speaks both
- OR: comma-separate — `language=FR,NL` → speaks either

### Chaining and reverse chaining

```
GET [base]/Observation?patient.name=peter          # chained
GET [base]/Patient?_has:Observation:patient:code=1234  # reverse chain
```

### Includes

```
GET [base]/MedicationRequest?patient=123
  &_include=MedicationRequest:medication
  &_revinclude=Provenance:target
  &_include:iterate=MedicationRequest:requester
```

### Missing data safety

Queries that filter by a coded value silently exclude resources where that element is absent. For safety-critical searches (e.g. allergies):

```
# Two separate queries (cannot be combined in one)
GET [base]/AllergyIntolerance?clinical-status=active
GET [base]/AllergyIntolerance?clinical-status:missing=true
```

Consider using Bundle type `batch` to issue both in one round-trip.

### Composite search parameters

Join sub-parameters with `$`. Used when AND semantics must apply to *the same* repeating element (e.g. same Observation.component):

```
GET [base]/Observation?component-code-value-quantity=http://loinc.org|8480-6$lt60
```

---

## 2. Operations ($)

### Common operations

| Operation | Scope | Purpose |
|-----------|-------|---------|
| `$validate` | type, instance | Validate resource against base spec or a profile |
| `$everything` | Patient, Encounter instance | Retrieve a patient's or encounter's full record |
| `$match` | Patient type | MPI-style probabilistic patient matching |
| `$expand` | ValueSet type, instance | Expand a value set for UI or validation |
| `$validate-code` | CodeSystem, ValueSet | Check if a code is valid in a code system / value set |
| `$lookup` | CodeSystem type | Get details for a code (display, properties) |
| `$translate` | ConceptMap type, instance | Map a code from one system to another |
| `$subsumes` | CodeSystem type, instance | Test is-a relationship between codes |
| `$document` | Composition instance | Generate a document Bundle from a Composition |
| `$apply` | PlanDefinition, ActivityDefinition | Apply a definition to produce request resources |
| `$evaluate-measure` | Measure type, instance | Run a quality measure |
| `$lastn` | Observation type | Most recent N observations per code |
| `$stats` | Observation type | Statistical summary of observations |
| `$process-message` | system | Process a message Bundle |
| `$closure` | system | Maintain a closure table for subsumption |

### Invocation patterns

```
# POST with Parameters resource (general form)
POST [base]/Patient/$match
Content-Type: application/fhir+json
{ "resourceType": "Parameters", "parameter": [...] }

# GET with URL params (only when affectsState=false and all params are primitive)
GET [base]/ValueSet/$expand?url=http://hl7.org/fhir/ValueSet/example&filter=abc

# POST with resource body (when exactly one input param is a Resource)
POST [base]/Resource/$validate
Content-Type: application/fhir+json
{ "resourceType": "Patient", ... }
```

---

## 3. Validation

### $validate operation

```
POST [base]/Patient/$validate?profile=http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient
Content-Type: application/fhir+json

{ "resourceType": "Patient", ... }
```

Returns an OperationOutcome with issues.

### What gets validated

- Structure and cardinality
- Value domains (data types, enumerations)
- Terminology bindings (Coding/CodeableConcept against ValueSets)
- FHIRPath invariants
- Profile constraints (slicing, extensions, min/max overrides)
- Questionnaire/QuestionnaireResponse alignment

### HTTP status codes for data quality

- **400** — resource couldn't be parsed or failed basic FHIR validation rules
- **422** — resource is valid FHIR but violates profiles or server business rules

### Postel's law guidance

> Be conservative in what you send, liberal in what you accept.

Validate strictly on *write paths*, especially narrative (security). Consider tolerating minor issues on *read paths* to avoid losing critical clinical data.

---

## 4. Workflow Patterns

### Definition → Request → Event

```
PlanDefinition ──$apply──▶ RequestGroup / ServiceRequest / MedicationRequest
                                        │
                                   fulfillment
                                        ▼
                              Procedure / Observation / DiagnosticReport
```

### Task-based coordination

Task tracks fulfillment across system boundaries. Task.focus references the request; Task.output references the result.

### Transactions

```
POST [base]
Content-Type: application/fhir+json

{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "fullUrl": "urn:uuid:...",
      "resource": { "resourceType": "Patient", ... },
      "request": { "method": "POST", "url": "Patient" }
    },
    {
      "resource": { "resourceType": "Observation", ...,
        "subject": { "reference": "urn:uuid:..." }
      },
      "request": { "method": "POST", "url": "Observation" }
    }
  ]
}
```

Transaction entries are processed atomically. Conditional references (`Patient?identifier=...`) resolve within the transaction.

---

## 5. Custom SearchParameter

When built-in search parameters don't cover a needed search path:

```json
{
  "resourceType": "SearchParameter",
  "url": "http://example.org/fhir/SearchParameter/observation-method-code",
  "name": "MethodCode",
  "status": "active",
  "description": "Search Observations by method code",
  "code": "method-code",
  "base": ["Observation"],
  "type": "token",
  "expression": "Observation.method.coding"
}
```

### Key fields

- `code` — the name used in the URL (`?method-code=...`)
- `base` — which resource type(s) this applies to
- `type` — search parameter type (token, reference, date, string, quantity, uri, composite, special)
- `expression` — FHIRPath that extracts the indexed values
- `comparator` / `modifier` / `chain` — declare which are supported
- `component` — for composite parameters, defines sub-parameter expressions

### Searching on extensions

Use FHIRPath `extension('url').value` syntax:

```json
{
  "expression": "Observation.extension('http://example.org/fhir/ext/priority').value as CodeableConcept"
}
```

---

## 6. Custom OperationDefinition

When the requirement involves server-side logic beyond CRUD + search:

```json
{
  "resourceType": "OperationDefinition",
  "url": "http://example.org/fhir/OperationDefinition/Encounter-risk-score",
  "name": "EncounterRiskScore",
  "status": "active",
  "kind": "operation",
  "code": "risk-score",
  "resource": ["Encounter"],
  "system": false,
  "type": false,
  "instance": true,
  "affectsState": false,
  "parameter": [
    {
      "name": "model",
      "use": "in",
      "min": 0,
      "max": "1",
      "type": "string",
      "documentation": "Which risk model to use"
    },
    {
      "name": "return",
      "use": "out",
      "min": 1,
      "max": "1",
      "type": "RiskAssessment",
      "documentation": "The computed risk assessment"
    }
  ]
}
```

Invocation: `GET [base]/Encounter/123/$risk-score?model=readmission`

### Named queries

Set `kind: query` to define a named query executed via `GET [base]/[type]?_query=[name]&params...`. All parameters must be simple search types.

---

## 7. Design Decision Rules

1. **Prefer standard resources and profiles** — introduce custom structures only when the workflow cannot be represented cleanly with existing patterns.
2. **Prefer search over operations** — search is cacheable, composable, and broadly supported; operations are appropriate when the server must compute or coordinate.
3. **Prefer transactions over sequential writes** — when multiple resources must be created/updated atomically.
4. **Check the CapabilityStatement** — server capabilities vary; design for graceful degradation.
5. **Make lifecycle ownership explicit** — who creates, updates, and is authoritative for each resource.
6. **Separate workflow from data model** — business process decisions (who does what, when) are distinct from FHIR resource choices.
