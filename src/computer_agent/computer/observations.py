from dataclasses import dataclass

from playwright.async_api import Page


_INTERACTIVE_SELECTOR = ", ".join(
    (
        "a[href]",
        "button",
        "input:not([type='hidden'])",
        "select",
        "textarea",
        "[role~='button']",
        "[role~='link']",
        "[role~='textbox']",
        "[role~='checkbox']",
        "[role~='radio']",
        "[role~='combobox']",
        "[role~='listbox']",
        "[role~='option']",
        "[role~='searchbox']",
        "[role~='switch']",
        "[role~='menuitem']",
        "[role~='tab']",
        "[role~='slider']",
        "[role~='spinbutton']",
        "[tabindex]:not([tabindex='-1'])",
        "[contenteditable='true']",
    )
)

_READ_INTERACTIVE_ELEMENTS = """
elements => {
    const isVisible = element => {
        const style = window.getComputedStyle(element);
        return style.display !== "none"
            && style.visibility !== "hidden"
            && !element.closest('[hidden], [inert], [aria-hidden="true"]')
            && element.getClientRects().length > 0;
    };

    const implicitRole = element => {
        const tag = element.tagName.toLowerCase();

        if (tag === "a" && element.hasAttribute("href")) return "link";
        if (tag === "button") return "button";
        if (tag === "textarea") return "textbox";
        if (tag === "select") {
            return element.multiple || element.size > 1 ? "listbox" : "combobox";
        }
        if (element.isContentEditable) return "textbox";
        if (tag !== "input") return null;

        switch (element.type.toLowerCase()) {
            case "button":
            case "submit":
            case "reset":
            case "image":
                return "button";
            case "checkbox":
                return "checkbox";
            case "radio":
                return "radio";
            case "range":
                return "slider";
            case "number":
                return "spinbutton";
            case "search":
                return "searchbox";
            default:
                return "textbox";
        }
    };

    const accessibleName = element => {
        const labelledBy = element.getAttribute("aria-labelledby");
        if (labelledBy) {
            const text = labelledBy
                .split(/\\s+/)
                .map(id => document.getElementById(id)?.innerText.trim() ?? "")
                .filter(Boolean)
                .join(" ");
            if (text) return text;
        }

        const ariaLabel = element.getAttribute("aria-label")?.trim();
        if (ariaLabel) return ariaLabel;

        const labels = "labels" in element ? Array.from(element.labels) : [];
        const labelText = labels
            .map(label => label.innerText.trim())
            .filter(Boolean)
            .join(" ");
        if (labelText) return labelText;

        const value = element.getAttribute("value")?.trim();
        if (value && ["button", "submit", "reset", "image"].includes(element.type)) {
            return value;
        }

        const text = element.innerText?.trim();
        if (text) return text;

        const placeholder = element.getAttribute("placeholder")?.trim();
        if (placeholder) return placeholder;

        const title = element.getAttribute("title")?.trim();
        return title || null;
    };

    return elements
        .filter(isVisible)
        .map(element => {
            const explicitRole = element.getAttribute("role")
                ?.trim()
                .split(/\\s+/)[0]
                .toLowerCase();
            const role = explicitRole || implicitRole(element);
            const ariaDisabled = element.getAttribute("aria-disabled")
                ?.toLowerCase() === "true";

            return {
                role,
                accessible_name: accessibleName(element),
                tag: element.tagName.toLowerCase(),
                input_type: element instanceof HTMLInputElement ? element.type : null,
                disabled: element.matches(":disabled") || ariaDisabled,
                href: element instanceof HTMLAnchorElement ? element.href : null,
            };
        });
}
"""


@dataclass(frozen=True)
class InteractiveElement:
    role: str | None
    accessible_name: str | None
    tag: str
    input_type: str | None
    disabled: bool
    href: str | None


@dataclass(frozen=True)
class PageObservation:
    title: str
    url: str
    status_text: str | None
    page_text: str
    record_count: int
    textbox_count: int
    button_count: int
    interactive_elements: tuple[InteractiveElement, ...]


async def observe_page(page: Page) -> PageObservation:
    status_locator = page.get_by_role("status")
    status_text = None
    if await status_locator.count():
        status_text = await status_locator.first.inner_text()

    raw_elements = await page.locator(_INTERACTIVE_SELECTOR).evaluate_all(
        _READ_INTERACTIVE_ELEMENTS
    )
    page_text = (await page.locator("body").inner_text())[:4_000]
    record_count = await page.locator("[data-record]").count()
    elements = tuple(
        InteractiveElement(
            role=element["role"],
            accessible_name=element["accessible_name"],
            tag=element["tag"],
            input_type=element["input_type"],
            disabled=element["disabled"],
            href=element["href"],
        )
        for element in raw_elements
    )

    return PageObservation(
        title=await page.title(),
        url=page.url,
        status_text=status_text,
        page_text=page_text,
        record_count=record_count,
        textbox_count=sum(element.role == "textbox" for element in elements),
        button_count=sum(element.role == "button" for element in elements),
        interactive_elements=elements,
    )
