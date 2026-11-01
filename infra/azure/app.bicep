targetScope = 'resourceGroup'

@description('An already approved Container Apps environment; this module does not create it.')
param environmentId string
param location string = resourceGroup().location
param appName string = 'mlb-predictor'
param workerName string = 'mlb-predictor-worker'

@description('Private release image pinned as registry/repository@sha256:digest.')
@minLength(1)
param image string
param registryServer string
param registryUsername string
@secure()
param registryPassword string

@description('Read-only API database role. Must require TLS on hosted PostgreSQL.')
@secure()
param apiDatabaseUrl string
@description('Separate writer role for future approved ingestion/prediction executions.')
@secure()
param workerDatabaseUrl string

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        allowInsecure: false
        targetPort: 8000
        transport: 'http'
      }
      secrets: [
        { name: 'database-url', value: apiDatabaseUrl }
        { name: 'registry-token', value: registryPassword }
      ]
      registries: [
        { server: registryServer, username: registryUsername, passwordSecretRef: 'registry-token' }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: image
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'MLB_DATABASE_URL', secretRef: 'database-url' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health/live', port: 8000, scheme: 'HTTP' }
              periodSeconds: 5
              failureThreshold: 30
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health/live', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 30
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health/ready', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 10
              periodSeconds: 15
              timeoutSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: '10' } } }
        ]
      }
    }
  }
}

// Deliberately no timer or live polling. First manual run only inspects DB state.
resource worker 'Microsoft.App/jobs@2025-01-01' = {
  name: workerName
  location: location
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 1
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      secrets: [
        { name: 'database-url', value: workerDatabaseUrl }
        { name: 'registry-token', value: registryPassword }
      ]
      registries: [
        { server: registryServer, username: registryUsername, passwordSecretRef: 'registry-token' }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: image
          command: ['mlb-predictor']
          args: ['watcher-status']
          resources: { cpu: json('1'), memory: '2Gi' }
          env: [
            { name: 'MLB_DATABASE_URL', secretRef: 'database-url' }
          ]
        }
      ]
    }
  }
}

output appResourceId string = app.id
output workerResourceId string = worker.id
