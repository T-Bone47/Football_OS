import React from "react";

export function Link({ to, children, ...rest }) {
  const href = typeof to === "string" ? to : "#";
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}

export function MemoryRouter({ children }) {
  return children;
}

/**
 * The stub stands in for the router in component tests, so there is no router
 * context: components that can render without one (links) fall back to plain
 * anchors, exactly as they do in production outside a Router.
 */
export function useInRouterContext() {
  return false;
}
