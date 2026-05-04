// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MiniProject",
    dependencies: [
        // GitHub-hosted dep (resolved via Package.resolved)
        .package(url: "https://github.com/horizontalsystems/EvmKit.Swift.git", from: "1.5.0"),
        // Another GitHub dep
        .package(url: "https://github.com/apple/swift-collections", exact: "1.1.4"),
    ],
    targets: [
        .target(
            name: "MiniProject",
            dependencies: [
                .product(name: "EvmKit", package: "EvmKit.Swift"),
                .product(name: "Collections", package: "swift-collections"),
            ]
        )
    ]
)
