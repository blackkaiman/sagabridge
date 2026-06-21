<?php
/**
 * SAGABridge Landing — minimal theme setup.
 */

if (!defined('ABSPATH')) { exit; }

/**
 * Enqueue style.css so WordPress loads it (and lets us add cache busting).
 */
function sagabridge_enqueue_assets() {
    wp_enqueue_style(
        'sagabridge-style',
        get_stylesheet_uri(),
        array(),
        '1.0'
    );
}
add_action('wp_enqueue_scripts', 'sagabridge_enqueue_assets');

/**
 * Basic theme support.
 */
function sagabridge_theme_setup() {
    add_theme_support('title-tag');
    add_theme_support('automatic-feed-links');
    add_theme_support('html5', array('search-form', 'comment-form', 'comment-list', 'gallery', 'caption'));
    add_theme_support('responsive-embeds');
}
add_action('after_setup_theme', 'sagabridge_theme_setup');
