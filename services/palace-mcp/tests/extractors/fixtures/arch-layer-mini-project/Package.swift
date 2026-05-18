// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "ArchLayerMini",
    products: [
        .library(name: "WalletCore", targets: ["WalletCore"]),
        .library(name: "WalletUI", targets: ["WalletUI"]),
    ],
    targets: [
        .target(
            name: "WalletCore",
            dependencies: [],
            path: "Sources/Core"
        ),
        .target(
            name: "WalletUI",
            dependencies: ["WalletCore"],
            path: "Sources/UI"
        ),
    ]
)
