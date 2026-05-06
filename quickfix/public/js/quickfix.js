// public/js/quickfix.js

frappe.provide("quickfix");

$(document).ready(function () {

    // wait for frappe desk to fully load
    frappe.after_ajax(function () {
        show_shop_name_in_navbar();
    });
});

function show_shop_name_in_navbar() {

    // get from boot object
    const shop_name = frappe.boot.quickfix_shop_name;

    // exit if no shop name
    if (!shop_name) {
        return;
    }

    // try different navbar selectors
    // frappe navbar structure varies by version
    const navbar =
        document.querySelector("*");

    if (!navbar) {
        console.warn("Quickfix: navbar not found");
        return;
    }

    // check if already added (prevent duplicates)
    if (document.getElementById("quickfix-shop-name")) {
        return;
    }

    // create element
    const el = document.createElement("div");
    el.id          = "quickfix-shop-name";
    el.innerText   = shop_name;
    el.style.cssText = `
        font-size   : 1rem;
        font-weight : bold;
        color       : #fff;
        margin-left : 15px;
        display     : flex;
        align-items : center;
        white-space : nowrap;
    `;

    navbar.appendChild(el);
}