// Copyright (c) 2022, Drayang Chua and contributors
// Ported to fact_frepple on v17; original at msf4-0/ERPNext-Frepple-Integration.
// For license information, please see license.txt

frappe.pages['manufacturing-order-page'].on_page_load = (wrapper) => {
	const page = frappe.ui.make_app_page({
		'parent': wrapper,
		'title': 'Frepple Manufacturing Order Page',
		'single_column': true
	});
	new ManufacturingOrderPage(page, wrapper);
};

class ManufacturingOrderPage {
	constructor(page, wrapper) {
		this.wrapper = wrapper;
		this.pageMain = $(page.main);
		this.showIframe();
	}

	showIframe() {
		this.getSettings().then(
			(r) => {
				this.URL = r.message;
				if (this.URL) {
					const safeURL = frappe.utils.escape_html(this.URL);
					const iFrameHtml = `
						<iframe
							src="${safeURL}"
							width="100%"
							height="590"
							marginwidth="0"
							marginheight="0"
							frameborder="no"
							scrolling="yes"
						/>
					`;
					this.iFrame = $(iFrameHtml).appendTo(this.pageMain);
				}
			}
		);
	}

	getSettings() {
		return frappe.call({
			'method': 'fact_frepple.fact_frepple.doctype.manufacturing_order_page.manufacturing_order_page.get_iframe_url'
		});
	}
}
