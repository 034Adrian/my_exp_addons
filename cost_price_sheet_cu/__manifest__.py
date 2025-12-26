{
    'name': 'Cost-Price Sheet CU',
    'summary' : 'Fichas de costo y precio',
    'version': '19.0.0.1',
    'author': 'Adrian Mesa Sacasas - Rulerhub',
    'License' : '',
    'category': 'Accounting/Cost',
    'depends': [
        'base', 'account', 'sale', 'purchase', 'stock', 'l10n_cu'
    ],
    'data': [
        "security/cost_price_sheet_security.xml",
        "security/ir.model.access.csv",
        "data/cost_price_sheet_sequence.xml",
        "views/cost_component_views.xml",
        "views/cost_price_sheet_report.xml",
    ],
    'aplication': True
}