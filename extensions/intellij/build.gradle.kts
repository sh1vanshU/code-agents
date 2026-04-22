plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.2.0"
    id("org.jetbrains.intellij.platform") version "2.2.1"
}

group = providers.gradleProperty("pluginGroup").get()
version = providers.gradleProperty("pluginVersion").get()

// Auto-detect local IntelliJ installation
fun findLocalIde(): String? {
    val home = System.getProperty("user.home")
    val candidates = listOf(
        // macOS
        "/Applications/IntelliJ IDEA.app/Contents",
        "/Applications/IntelliJ IDEA CE.app/Contents",
        "/Applications/IntelliJ IDEA Ultimate.app/Contents",
        "$home/Applications/IntelliJ IDEA.app/Contents",
        // Linux
        "$home/.local/share/JetBrains/IntelliJ IDEA/Contents",
        "/opt/idea/Contents",
        "/snap/intellij-idea-ultimate/current/ide",
        "/snap/intellij-idea-community/current/ide",
        // Windows
        "C:/Program Files/JetBrains/IntelliJ IDEA/Contents",
    )
    return candidates.firstOrNull { path ->
        File(path).isDirectory &&
        (File("$path/lib/app.jar").exists() || File("$path/lib/platform-loader.jar").exists())
    }
}

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    intellijPlatform {
        // Priority: explicit property > auto-detected local IDE > Maven download
        val explicitLocalPath = providers.gradleProperty("platformLocalPath").orNull
        val localIdePath = explicitLocalPath ?: findLocalIde()

        if (localIdePath != null && File(localIdePath).isDirectory) {
            logger.lifecycle("Using local IntelliJ IDE: $localIdePath")
            local(localIdePath)
        } else {
            val type = providers.gradleProperty("platformType")
            val version = providers.gradleProperty("platformVersion")
            logger.lifecycle("Downloading IntelliJ Platform: ${type.get()} ${version.get()}")
            create(type, version)
        }
        pluginVerifier()
    }

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.11.0")

    testImplementation("junit:junit:4.13.2")
}

intellijPlatform {
    pluginConfiguration {
        name = providers.gradleProperty("pluginName")
        version = providers.gradleProperty("pluginVersion")

        ideaVersion {
            sinceBuild = "241"    // Supports 2024.1+
            untilBuild = provider { null }  // No upper bound
        }
    }

    pluginVerification {
        ides {
            recommended()
        }
    }
}

kotlin {
    jvmToolchain(21)
}

tasks {
    wrapper {
        gradleVersion = "8.13"
    }
    // Skip buildSearchableOptions — requires full IDE launch, may fail with local platform
    named("buildSearchableOptions") {
        enabled = false
    }
}
