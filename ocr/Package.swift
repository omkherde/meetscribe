// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ocrtext",
    platforms: [.macOS("14.2")],
    targets: [
        .executableTarget(name: "ocrtext", path: "Sources/ocrtext")
    ]
)
