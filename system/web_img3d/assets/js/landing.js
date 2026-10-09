const menuToggle = document.querySelector('[data-nav-toggle]');
const navigation = document.querySelector('[data-nav]');
const navigationLinks = document.querySelectorAll('[data-nav-link]');
const revealElements = document.querySelectorAll('.img3d-reveal');
const sectionLinks = new Map();

function closeMenu() {
    if (!menuToggle || !navigation) {
        return;
    }

    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', menuToggle.dataset.openLabel);
    navigation.classList.remove('img3d-nav-open');
}

if (menuToggle && navigation) {
    menuToggle.dataset.openLabel = menuToggle.dataset.navOpenLabel || '';
    menuToggle.dataset.closeLabel = menuToggle.dataset.navCloseLabel || '';

    menuToggle.addEventListener('click', () => {
        const isExpanded = menuToggle.getAttribute('aria-expanded') === 'true';
        menuToggle.setAttribute('aria-expanded', String(!isExpanded));
        menuToggle.setAttribute(
            'aria-label',
            isExpanded ? menuToggle.dataset.openLabel : menuToggle.dataset.closeLabel
        );
        navigation.classList.toggle('img3d-nav-open', !isExpanded);
    });

    navigationLinks.forEach((link) => link.addEventListener('click', closeMenu));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeMenu();
            menuToggle.focus();
        }
    });
    window.addEventListener('resize', () => {
        if (window.innerWidth > 760) {
            closeMenu();
        }
    });
}

const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
if (motionPreference.matches || !('IntersectionObserver' in window)) {
    revealElements.forEach((element) => element.classList.add('img3d-visible'));
} else {
    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('img3d-visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12 });

    revealElements.forEach((element) => revealObserver.observe(element));
}

navigationLinks.forEach((link) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (target) {
        sectionLinks.set(target, link);
    }
});

if ('IntersectionObserver' in window && sectionLinks.size) {
    const activeLinkObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) {
                return;
            }

            sectionLinks.forEach((link) => link.classList.remove('img3d-nav-active'));
            sectionLinks.get(entry.target)?.classList.add('img3d-nav-active');
        });
    }, { rootMargin: '-25% 0px -65% 0px' });

    sectionLinks.forEach((_, section) => activeLinkObserver.observe(section));
}
