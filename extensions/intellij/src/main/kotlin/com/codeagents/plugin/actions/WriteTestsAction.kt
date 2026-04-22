package com.codeagents.plugin.actions

class WriteTestsAction : BaseAgentAction("code-tester") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return if (selectedText.isNotBlank())
            "Write comprehensive tests for this code from $fileName:\n\n```$languageId\n$selectedText\n```"
        else
            "Write tests for the file: $filePath"
    }
}
