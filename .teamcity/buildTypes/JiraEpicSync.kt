package buildTypes

import jetbrains.buildServer.configs.kotlin.*
import jetbrains.buildServer.configs.kotlin.buildSteps.script
import jetbrains.buildServer.configs.kotlin.triggers.schedule

object JiraEpicSync : BuildType({
    name = "Jira epic sync"
    description = "Synchronizes issues under the configured Jira epic to GitHub every hour."
    maxRunningBuilds = 1

    vcs {
        root(DslContext.settingsRoot)
    }

    params {
        param("env.GITHUB_APP_ID", DslContext.getParameter("github-app-id"))
        param("env.GITHUB_APP_INSTALLATION_ID", DslContext.getParameter("github-app-installation-id"))
        password("env.GITHUB_APP_PRIVATE_KEY", DslContext.getParameter("github-app-private-key"), display = ParameterDisplay.HIDDEN)
    }

    steps {
        script {
            name = "Sync Jira to GitHub (Jira read-only)"
            scriptContent = """
                pip install ./.teamcity/jira_sync
                python -m jira_sync.epic_sync
            """.trimIndent()
            dockerImage = "containers.deltares.nl/docker-proxy/python:3.12-slim"
        }
    }

    triggers {
        schedule {
            schedulingPolicy = cron {
                minutes = "0"
            }
            branchFilter = "+:<default>"
            triggerBuild = always()
            withPendingChangesOnly = false
        }
    }

    requirements {
        equals("teamcity.agent.jvm.os.name", "Linux")
        equals("docker.server.osType", "linux")
    }
})
