// swift-tools-version: 5.8
import PackageDescription

let package = Package(
    name: "DeadSymbolMiniProject",
    products: [
        .library(name: "DeadSymbolMiniCore", targets: ["DeadSymbolMiniCore"]),
        .executable(name: "DeadSymbolMiniApp", targets: ["DeadSymbolMiniApp"]),
    ],
    targets: [
        .target(name: "DeadSymbolMiniCore"),
        .executableTarget(
            name: "DeadSymbolMiniApp",
            dependencies: ["DeadSymbolMiniCore"]
        ),
    ]
)
