package com.codeagents.plugin.actions

class ReviewCodeAction : BaseAgentAction("code-reviewer") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return if (selectedText.isNotBlank())
            "Review this code for bugs, security issues, and improvements:\n\n```$languageId\n$selectedText\n```"
        else
            "Review the file: $filePath"
    }
}
