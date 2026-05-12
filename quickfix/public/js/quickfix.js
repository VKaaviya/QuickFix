// public/js/quickfix.js

frappe.provide("quickfix");

$(document).ready(function () {

    frappe.after_ajax(function () {
        show_shop_name_in_navbar();
    });
});

function show_shop_name_in_navbar() {
    const shop_name = frappe.boot.quickfix_shop_name;

    if (!shop_name) {
        return;
    }
    const navbar =
        document.querySelector("*");

    if (!navbar) {
        console.warn("Quickfix: navbar not found");
        return;
    }

    if (document.getElementById("quickfix-shop-name")) {
        return;
    }

   
    const el = document.createElement("div");
    el.id          = "quickfix-shop-name";
    el.innerText   = shop_name;
    el.style.cssText = `
        font-size   : 1rem;
        font-weight : bold;
        color       :#fff;
        margin-left : 15px;
        display     : flex;
        align-items : center;
        white-space : nowrap;
    `;

    navbar.appendChild(el);
}