// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "UwMiniCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .library(name: "UwMiniCore", targets: ["UwMiniCore"]),
        .executable(name: "UwMiniApp", targets: ["UwMiniApp"]),
    ],
    targets: [
        .target(name: "UwMiniCore"),
        .target(name: "Foo", dependencies: ["UwMiniCore"], path: "Pods/Foo"),
        .executableTarget(name: "UwMiniApp", dependencies: ["UwMiniCore", "Foo"]),
    ]
)
