import NeedleFoundation

protocol WalletDependency: Dependency {
    var api: WalletAPI { get }
}
