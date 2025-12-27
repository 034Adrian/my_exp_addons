{
    'name': 'Cost-Price Sheet CU',
    'summary': 'Fichas de costo y precio',
    'version': '19.0.1.0.0',
    'author': 'Adrian Mesa Sacasas - Rulerhub',
    'license': 'AGPL-3',
    'category': 'Accounting',
    'images': ['static/description/Prinz-Eugen.png'],
    'depends': [
        'base', 'mail', 'product', 'account', 'sale', 'purchase', 'stock'
    ],
    'data': [
        'security/cost_price_sheet_security.xml',
        'security/ir.model.access.csv',
        'data/cost_price_sheet_sequence.xml',
        'views/cost_component_views.xml',
        'report/cost_price_sheet_report.xml',
    ],
    'installable': True,
    'application': True,
}