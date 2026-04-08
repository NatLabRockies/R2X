// Prevent navigation to index pages in the sidebar, only allow expand/collapse
document.addEventListener("DOMContentLoaded", function () {
  // Find all links in the sidebar that point to index.html files
  const sidebarLinks = document.querySelectorAll(".sidebar-tree a, .toctree a");

  sidebarLinks.forEach(function (link) {
    const href = link.getAttribute("href");

    // Check if this link points to any index.html file (relative or absolute path)
    const isIndexPage =
      href && (href.includes("/index.html") || href.endsWith("index.html"));

    // Check if this is within the how-tos section
    const isHowTosSection = href && href.includes("how-tos");

    if (isIndexPage && isHowTosSection) {
      // Find the parent li element
      const parentLi = link.closest("li");

      if (parentLi) {
        // Add click handler to prevent navigation
        link.addEventListener("click", function (event) {
          // Prevent the default navigation behavior
          event.preventDefault();
          event.stopPropagation();

          // Find the checkbox in the parent li
          const checkbox = parentLi.querySelector("input.toctree-checkbox");

          if (checkbox) {
            // Toggle the checkbox to expand/collapse
            checkbox.checked = !checkbox.checked;
          }

          return false;
        });

        // Keep normal cursor to indicate it's clickable
        link.style.cursor = "pointer";
      }
    }
  });
});
