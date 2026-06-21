MERGE (p:Project {slug: 'test-native'})
SET p.group_id = 'project/test-native',
    p.cm_project_name = 'Users-fixture-test-native';

MERGE (f:File {project_id: 'project/test-native', path: 'src/wallet.py'})
SET f.group_id = 'project/test-native',
    f.file_path = 'src/wallet.py',
    f.language = 'python';

MERGE (m:Module {project_id: 'project/test-native', slug: 'WalletCore'})
SET m.group_id = 'project/test-native',
    m.name = 'WalletCore',
    m.kind = 'python_package',
    m.manifest_path = 'pyproject.toml',
    m.source_root = 'src';

MERGE (l:Layer {project_id: 'project/test-native', name: 'core'})
SET l.group_id = 'project/test-native',
    l.rule_source = '.palace/architecture-rules.yaml';

MERGE (d:ExternalDependency {purl: 'pkg:pypi/httpx@0.27.0'})
SET d.ecosystem = 'pypi',
    d.resolved_version = '0.27.0';

MATCH (p:Project {slug: 'test-native'}), (d:ExternalDependency {purl: 'pkg:pypi/httpx@0.27.0'})
MERGE (p)-[pd:DEPENDS_ON]->(d)
SET pd.scope = 'main',
    pd.declared_in = 'pyproject.toml',
    pd.declared_version_constraint = '^0.27';

MERGE (bootstrap:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.bootstrap'})
SET bootstrap.name = 'bootstrap',
    bootstrap.short_name = 'bootstrap',
    bootstrap.file_path = 'src/wallet.py',
    bootstrap.kind = 'function',
    bootstrap.module_name = 'WalletCore',
    bootstrap.is_main_entry = true;

MERGE (helper:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.helper'})
SET helper.name = 'helper',
    helper.short_name = 'helper',
    helper.file_path = 'src/wallet.py',
    helper.kind = 'function',
    helper.module_name = 'WalletCore';

MATCH (bootstrap:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.bootstrap'}),
      (helper:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.helper'})
MERGE (bootstrap)-[:CALLS]->(helper);

MATCH (f:File {project_id: 'project/test-native', path: 'src/wallet.py'}),
      (bootstrap:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.bootstrap'}),
      (helper:Symbol {group_id: 'project/test-native', qualified_name: 'wallet.helper'})
MERGE (f)-[:CONTAINS]->(bootstrap)
MERGE (f)-[:CONTAINS]->(helper)
MERGE (bootstrap)-[:DEFINED_IN]->(f)
MERGE (helper)-[:DEFINED_IN]->(f);

MERGE (fn_bootstrap:Function {project_id: 'project/test-native', path: 'src/wallet.py', name: 'bootstrap', start_line: 1})
SET fn_bootstrap.group_id = 'project/test-native',
    fn_bootstrap.file_path = 'src/wallet.py',
    fn_bootstrap.qualified_name = 'wallet.bootstrap',
    fn_bootstrap.end_line = 2,
    fn_bootstrap.language = 'python';

MERGE (fn_helper:Function {project_id: 'project/test-native', path: 'src/wallet.py', name: 'helper', start_line: 4})
SET fn_helper.group_id = 'project/test-native',
    fn_helper.file_path = 'src/wallet.py',
    fn_helper.qualified_name = 'wallet.helper',
    fn_helper.end_line = 5,
    fn_helper.language = 'python';

MATCH (f:File {project_id: 'project/test-native', path: 'src/wallet.py'}),
      (fn_bootstrap:Function {project_id: 'project/test-native', path: 'src/wallet.py', name: 'bootstrap', start_line: 1}),
      (fn_helper:Function {project_id: 'project/test-native', path: 'src/wallet.py', name: 'helper', start_line: 4})
MERGE (f)-[:CONTAINS]->(fn_bootstrap)
MERGE (f)-[:CONTAINS]->(fn_helper);
