package com.codeagents.plugin.actions

class ExplainCodeAction : BaseAgentAction("code-reasoning") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return if (selectedText.isNotBlank())
            "Explain what this code does, its architecture, and design patterns:\n\n```$languageId\n$selectedText\n```"
        else
            "Explain the file: $filePath"
    }
}
