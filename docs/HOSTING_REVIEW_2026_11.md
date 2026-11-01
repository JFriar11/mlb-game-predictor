# Hosting review — 2026-11-01

All-Azure remains the provisional operational preference, pending user selection
and an account/region-specific quote. No resources have been created. The August
$16–18 estimate predates the web application and revised worker memory; it is a
historical estimate, not a current complete-system quote.

Azure Container Apps advertises a subscription-wide monthly grant of 180,000
vCPU-seconds, 360,000 GiB-seconds and two million requests. Jobs have no execution
charge while idle; an active public web app changes total usage. Region-specific
prices were not available as numeric quotes from the dynamic page. PostgreSQL,
registry, logs, backups and networking also require a quote.
Sources: [Container Apps pricing](https://azure.microsoft.com/en-us/pricing/details/container-apps/),
[PostgreSQL pricing](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/),
[Jobs lifecycle](https://learn.microsoft.com/en-us/azure/container-apps/jobs).

Neon's current Free plan lists 1 GB storage, 100 CU-hours and 5 GB public transfer
per month. Paid Launch lists $0.106/CU-hour and $0.35/GB-month. These are provider
rates, not this project's monthly cost. The builder's repeated historical reads
make a near-zero cross-cloud transfer assumption unsafe. Withdraw the earlier
free-tier recommendation until measured transfer and data reuse establish fit.
Source: [Neon pricing](https://neon.com/pricing).

Before deployment, choose the provider/account, region, monthly ceiling, registry,
and audience/access policy. Recheck prices at that point. The prepared Azure
module uses existing resources, private ingress and a manual status job; it does
not establish a complete production network, identity or monitoring environment.
