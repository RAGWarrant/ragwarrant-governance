param location string = resourceGroup().location
param containerAppEnvironmentName string = 'ragwarrant-env'
param jobName string = 'ragwarrant-governance-job'
param image string = 'RAGWARRANT_IMAGE_REFERENCE_PLACEHOLDER'

resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: containerAppEnvironmentName
  location: location
}

resource job 'Microsoft.App/jobs@2023-05-01' = {
  name: jobName
  location: location
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
    }
    template: {
      containers: [
        {
          name: 'ragwarrant'
          image: image
          args: [
            'run-governance-job'
            '--config'
            '/inputs/public_mini_governance_job.yaml'
            '--output-root'
            '/outputs'
            '--decision-out'
            '/outputs/promotion_decision.json'
          ]
          env: [
            {
              name: 'RAGWARRANT_STORAGE_MODE'
              value: 'local'
            }
            {
              name: 'RAGWARRANT_INPUT_DIR'
              value: '/inputs'
            }
            {
              name: 'RAGWARRANT_OUTPUT_DIR'
              value: '/outputs'
            }
          ]
        }
      ]
    }
  }
}
