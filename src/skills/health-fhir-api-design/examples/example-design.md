# FHIR R4 API Design — Example Output

**Skill**: `health-fhir-api-design` (mode: design)
**Date**: 2026-03-20

---

## Requirements

A care coordination platform needs to:

1. Retrieve a patient's active medications with prescriber details
2. Find all lab results for a patient from the last 90 days, flagging abnormals
3. Create a referral order with supporting diagnoses as a single atomic transaction

---

## Requirement 1: Active Medications with Prescriber

### Resources Involved

- `MedicationRequest` — represents prescribed medications
- `Practitioner` — the prescriber
- US Core MedicationRequest profile preferred (`http://hl7.org/fhir/us/core/StructureDefinition/us-core-medicationrequest`)

### Interaction

```http
GET [base]/MedicationRequest?patient=Patient/12345&status=active&_include=MedicationRequest:requester&_sort=-authoredon
```

### Search Parameters

| Parameter | Type | Value | Notes |
| --- | --- | --- | --- |
| `patient` | reference | `Patient/12345` | Standard R4 search param |
| `status` | token | `active` | Filters to current medications |
| `_include` | special | `MedicationRequest:requester` | Pulls in Practitioner resources |
| `_sort` | special | `-authoredon` | Most recent first |

### Missing-Data Safety

Medications where `status` is absent will not match `status=active`. To retrieve both active medications and those with a missing status, issue two separate queries (they cannot be combined in a single query):

```http
GET [base]/MedicationRequest?patient=Patient/12345&status=active
GET [base]/MedicationRequest?patient=Patient/12345&status:missing=true
```

Consider using a Bundle `batch` to issue both in a single round-trip.

> Note: `status=active,unknown` uses OR semantics and matches only resources where `status` is explicitly set to `active` **or** `unknown` — it does not match resources where `status` is absent.

### Trade-Offs

- **`_include` support**: widely supported but not required by the spec. If the server doesn't support it, fall back to collecting `requester` references and issuing a batch read.
- **Medication reference vs inline**: `MedicationRequest.medicationReference` requires a follow-up `_include=MedicationRequest:medication` to get the Medication resource. `MedicationRequest.medicationCodeableConcept` is inline. Check the server's CapabilityStatement.
- **Pagination**: if the patient has many medications, the server may return a paginated Bundle. Follow `Bundle.link` with `relation = "next"`.

### R4 Spec References

- Search: https://hl7.org/fhir/R4/search.html
- MedicationRequest: https://hl7.org/fhir/R4/medicationrequest.html
- MedicationRequest search params: https://hl7.org/fhir/R4/medicationrequest.html#search

---

## Requirement 2: Lab Results from Last 90 Days

### Resources Involved

- `Observation` — lab results (category `laboratory`)
- US Core Laboratory Result Observation profile preferred

### Interaction

```http
GET [base]/Observation?patient=Patient/12345&category=laboratory&date=ge2025-12-20&_sort=-date&_count=100
```

### Search Parameters

| Parameter | Type | Value | Notes |
| --- | --- | --- | --- |
| `patient` | reference | `Patient/12345` | Standard |
| `category` | token | `laboratory` | Filters to lab results only |
| `date` | date | `ge2025-12-20` | 90 days before 2026-03-20 |
| `_sort` | special | `-date` | Most recent first |
| `_count` | special | `100` | Page size hint |

### Flagging Abnormals

Abnormal status is carried in `Observation.interpretation` (value set: `http://hl7.org/fhir/R4/valueset-observation-interpretation.html`). Common codes:

| Code | Display |
| --- | --- |
| `H` | High |
| `L` | Low |
| `HH` | Critical high |
| `LL` | Critical low |
| `A` | Abnormal |

The client should check `interpretation.coding.code` for these values. Do not rely solely on comparing `value` to `referenceRange` — not all Observations include reference ranges, and interpretation is the server's authoritative flag.

### Searching for Only Abnormals (Optional)

If the server supports a custom SearchParameter on `interpretation`:

```http
GET [base]/Observation?patient=Patient/12345&category=laboratory&date=ge2025-12-20&interpretation=H,L,HH,LL,A
```

> **Note**: `interpretation` is not a standard R4 search parameter for Observation. This requires a custom SearchParameter.

### Custom SearchParameter (if needed)

```json
{
  "resourceType": "SearchParameter",
  "url": "https://example.org/fhir/SearchParameter/observation-interpretation",
  "name": "interpretation",
  "status": "active",
  "code": "interpretation",
  "base": ["Observation"],
  "type": "token",
  "expression": "Observation.interpretation",
  "description": "Search by observation interpretation code"
}
```

### Trade-Offs

- **`$lastn` operation**: for getting only the most recent result per test code, use `GET [base]/Observation/$lastn?patient=Patient/12345&category=laboratory`. This is a standard R4 operation but not universally supported.
- **Date precision**: the `ge` prefix is inclusive. If the server stores times, `ge2025-12-20` includes all of December 20.
- **Pagination**: lab-heavy patients may have hundreds of results. The client must follow pagination links.

### R4 Spec References

- Observation: https://hl7.org/fhir/R4/observation.html
- Search prefixes: https://hl7.org/fhir/R4/search.html#prefix
- $lastn: https://hl7.org/fhir/R4/observation-operation-lastn.html

---

## Requirement 3: Referral Order with Supporting Diagnoses (Transaction)

### Resources Involved

- `ServiceRequest` — the referral order
- `Condition` — supporting diagnoses (if not already on the server)
- `Bundle` (type: `transaction`) — atomic write

### Interaction

```http
POST [base]
Content-Type: application/fhir+json
```

### Transaction Bundle

```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "fullUrl": "urn:uuid:condition-1",
      "resource": {
        "resourceType": "Condition",
        "clinicalStatus": {
          "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active" }]
        },
        "code": {
          "coding": [{ "system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus" }]
        },
        "subject": { "reference": "Patient/12345" }
      },
      "request": {
        "method": "POST",
        "url": "Condition",
        "ifNoneExist": "patient=Patient/12345&code=http://snomed.info/sct|44054006"
      }
    },
    {
      "fullUrl": "urn:uuid:referral-1",
      "resource": {
        "resourceType": "ServiceRequest",
        "status": "active",
        "intent": "order",
        "category": [
          {
            "coding": [{ "system": "http://snomed.info/sct", "code": "3457005", "display": "Patient referral" }]
          }
        ],
        "code": {
          "coding": [{ "system": "http://snomed.info/sct", "code": "183523005", "display": "Referral to endocrinology service" }]
          },
        "subject": { "reference": "Patient/12345" },
        "requester": { "reference": "Practitioner/67890" },
        "reasonReference": [{ "reference": "urn:uuid:condition-1" }],
        "authoredOn": "2026-03-20"
      },
      "request": {
        "method": "POST",
        "url": "ServiceRequest"
      }
    }
  ]
}
```

### Key Design Points

- **Conditional create** (`ifNoneExist`): prevents duplicate Condition resources if the diagnosis already exists on the server.
- **Internal references** (`urn:uuid:condition-1`): the ServiceRequest references the Condition created in the same transaction. The server resolves these after processing.
- **Atomicity**: if any entry fails, the entire transaction is rolled back. This is guaranteed by the `transaction` type (not `batch`).
- **Order of entries**: the server must process transaction entries in dependency order regardless of array position, but some servers process sequentially — placing the Condition before the ServiceRequest is safer.

### Trade-Offs

- **Transaction support**: required by the R4 spec for servers that declare it in their CapabilityStatement, but some lightweight servers support only `batch`. Check `CapabilityStatement.rest.interaction` for `transaction`.
- **Conditional create matching**: the `ifNoneExist` search must match the server's supported search parameters. If the server doesn't support `code` search on Condition, the conditional create will fail.
- **ServiceRequest vs Task**: `ServiceRequest` represents the clinical order. To track fulfillment status across organizations, pair it with a `Task` resource.

### R4 Spec References

- Bundle transactions: https://hl7.org/fhir/R4/http.html#transaction
- ServiceRequest: https://hl7.org/fhir/R4/servicerequest.html
- Conditional create: https://hl7.org/fhir/R4/http.html#ccreate
- Workflow patterns: https://hl7.org/fhir/R4/workflow.html
