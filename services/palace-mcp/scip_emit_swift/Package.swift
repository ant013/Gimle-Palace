// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "palace-swift-scip-emit",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "PalaceSwiftScipEmitCore", targets: ["PalaceSwiftScipEmitCore"]),
        .executable(name: "palace-swift-scip-emit-cli", targets: ["PalaceSwiftScipEmitCLI"]),
    ],
    dependencies: [
        .package(
            url: "https://github.com/swiftlang/indexstore-db.git",
            revision: "4ee7a49edc48e94361c3477623deeffb25dbed0d"
        ),
        .package(url: "https://github.com/apple/swift-protobuf.git", exact: "1.37.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.5.0"),
    ],
    targets: [
        .target(
            name: "PalaceSwiftScipEmitCore",
            dependencies: [
                .product(name: "IndexStoreDB", package: "indexstore-db"),
                .product(name: "SwiftProtobuf", package: "swift-protobuf"),
            ],
            exclude: ["Proto/scip.proto"]
        ),
        .executableTarget(
            name: "PalaceSwiftScipEmitCLI",
            dependencies: [
                "PalaceSwiftScipEmitCore",
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ]
        ),
        .testTarget(
            name: "PalaceSwiftScipEmitCoreTests",
            dependencies: ["PalaceSwiftScipEmitCore"]
        ),
    ]
)
