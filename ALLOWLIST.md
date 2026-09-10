# Athena IP allowlist runbook

Use this runbook to add or remove a public IP address with the Cloudflare MCP. Athena uses IP-only Cloudflare Access. It does not use user authentication.

## Security rules

- Keep real IP addresses out of Git, OneDrive, screenshots, and agent reports.
- Give every address a lowercase identifier, such as `office`, `jeiser-vargas`, or `guest-network`.
- Supply the identifier and address to the agent in the current private task only.
- Add one exact host rule per address: `/32` for IPv4 and `/128` for IPv6.
- Do not add a wider network unless Jeiser Vargas explicitly approves it.
- Never replace the complete allowlist with one new address.
- Stop if Cloudflare requests payment, an upgrade, or a metered product. Athena's Cloudflare cost limit is USD 0.00.

Cloudflare stores the CIDR value in the Access rule but does not store a label for each value. The identifier belongs in the private change request and the final redacted report. If a permanent private address-to-owner registry becomes necessary, store it in an approved password manager, not this repository.

Use these identifiers consistently:

| Identifier | Meaning |
| --- | --- |
| `office` | Main office public internet connection |
| `jeiser-vargas` | Jeiser Vargas's current public internet connection |

Add a clear suffix for another connection, such as `office-guest`, `jeiser-vargas-ipv6`, or `warehouse-1`.

## Address request format

Use one line per address:

```text
<identifier> | <public-ip-address>
```

Examples with safe placeholders:

```text
office | <OFFICE_PUBLIC_IPV4>
jeiser-vargas | <JEISER_PUBLIC_IPV4>
jeiser-vargas-ipv6 | <JEISER_PUBLIC_IPV6>
```

Normalize exact addresses before the update:

```text
office | <OFFICE_PUBLIC_IPV4>/32
jeiser-vargas | <JEISER_PUBLIC_IPV4>/32
jeiser-vargas-ipv6 | <JEISER_PUBLIC_IPV6>/128
```

Do not put the real values in this file. Reject private, loopback, link-local, multicast, malformed, or documentation-only addresses. Ask before accepting a CIDR wider than `/32` or `/128`.

## Copyable agent request

Paste the real address only into the private task that will run the change:

```text
Follow ALLOWLIST.md exactly. Use the Cloudflare MCP to add this address to Athena:

Identifier: office
Public IP: <PASTE_ADDRESS_HERE>

Do not print or save the address. Preserve every existing Access rule. Stop on any payment or upgrade request. Read the policy back and run the required access checks.
```

## Exact Cloudflare targets

| Item | Exact value |
| --- | --- |
| Protected Access application | `Athena IP-only access` |
| IP policy | `Approved Athena IPs` |
| Required policy action | `Bypass` |
| Production hostname | `athena-knowledge-portal.pages.dev` |
| Preview hostname | `*.athena-knowledge-portal.pages.dev` |
| Public guide application | `Athena public access guide` |
| Public guide policy | `Public request-access guide` |
| Public paths | `/request-access` and `/request-access.html` |

Do not edit or delete the public guide application or its policy while changing the IP allowlist.

## Add an address with the Cloudflare MCP

The Cloudflare MCP must be authenticated to the correct account and have `Access: Apps and Policies Write`. Use its current API search before execution because MCP operation schemas can change.

1. Search the Cloudflare API for the operation that lists Zero Trust Access applications for the current account.
2. Execute it and find exactly one application named `Athena IP-only access`. Stop if none or more than one exists.
3. List that application's policies. Find exactly one policy named `Approved Athena IPs`. Stop if none or more than one exists.
4. Read the complete current policy before changing it. Keep this response only in task memory; do not save it to a tracked file.
5. Confirm that the policy action is `Bypass`. Stop if it is different.
6. Validate the supplied public address with a standard IP-address parser. Convert an exact IPv4 address to `/32` or an exact IPv6 address to `/128`.
7. Check whether the normalized CIDR already exists. If it exists, make no update and report the identifier as already allowed.
8. Append one IP selector to the existing `include` rules. Preserve every existing `include`, `exclude`, `require`, name, action, and other policy field.
9. Search for and execute the current operation that updates one Access application policy. Send the complete preserved policy, not a partial replacement.
10. Read the policy again. Confirm all prior rules remain, the new CIDR occurs exactly once, and the action remains `Bypass`.

The update is unsafe if the agent did not first read and preserve the complete policy. A `PUT` can replace omitted fields.

## Verify access

1. From the newly approved network, confirm that `https://athena-knowledge-portal.pages.dev/` returns Athena.
2. From the same network, confirm that a current preview hostname also returns Athena.
3. From an independent, non-approved network, confirm that protected pages redirect to `/request-access` and do not expose Athena content.
4. Confirm that `/request-access` and `/request-access.html` remain public.

Do not claim blocked-network verification from the approved network. If an independent check is unavailable, report the configuration as updated but not externally validated.

## Remove or rotate an address

1. Get the identifier and exact current CIDR through a private request.
2. Read the complete current policy.
3. Remove only the exact matching CIDR. Stop if it is absent or occurs more than once.
4. Update the policy with all other fields and rules preserved.
5. Read it again and confirm that only the requested CIDR was removed.
6. Run the access checks above from an approved and a blocked network.

For rotation, add and verify the new address first. Remove the old address only after the new network works.

## Stop conditions

Stop without changing Cloudflare when:

- authentication or authorization returns `401` or `403`;
- the application or policy name is missing or ambiguous;
- the existing action is not `Bypass`;
- the address is invalid, non-public, or wider than an exact host rule without explicit approval;
- the current policy cannot be read in full;
- an update would remove or alter an unrelated rule;
- Cloudflare shows a payment, upgrade, or metered-feature requirement.

After a failed update, read the policy again before any retry. Never retry a replacement operation blindly.

## Redacted completion report

Report the result without the address:

```text
Identifier: office
Application: Athena IP-only access
Policy: Approved Athena IPs
Change: one IPv4 /32 host rule added
Readback: passed; prior rules preserved
Allowed-network test: passed
Blocked-network test: passed
Public request guide: passed
Cloudflare paid features: none enabled
```

## Official references

- [Cloudflare API documentation](https://developers.cloudflare.com/api/)
- [Cloudflare MCP server](https://github.com/cloudflare/mcp)
- [Update an Access policy](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/policies/methods/update/)
