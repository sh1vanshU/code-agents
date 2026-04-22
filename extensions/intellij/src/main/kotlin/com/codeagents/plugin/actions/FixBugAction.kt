package com.codeagents.plugin.actions

class FixBugAction : BaseAgentAction("code-writer") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return if (selectedText.isNotBlank())
            "Fix any bugs or issues in this code from $fileName:\n\n```$languageId\n$selectedText\n```"
        else
            "Fix bugs in the file: $filePath"
    }
}
