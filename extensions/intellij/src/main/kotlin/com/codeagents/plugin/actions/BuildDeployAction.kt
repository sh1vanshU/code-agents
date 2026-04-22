package com.codeagents.plugin.actions

class BuildDeployAction : BaseAgentAction("jenkins-cicd") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return "Build and deploy the current project"
    }
}
