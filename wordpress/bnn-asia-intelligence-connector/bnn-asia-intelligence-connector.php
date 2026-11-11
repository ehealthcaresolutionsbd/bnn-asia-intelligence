<?php
/**
 * Plugin Name:       BNN Asia Intelligence Connector
 * Description:       Shows BNN Asia country intelligence, Asia rankings and official index data from the BNN Asia Intelligence API (api.bnnasia.org). The API key stays on the server; visitors only receive public, published data.
 * Version:           1.0.1
 * Requires at least: 6.2
 * Requires PHP:      7.4
 * Author:            BNN Asia
 * License:           GPL-2.0-or-later
 * Text Domain:       bnn-intel
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'BNN_INTEL_VERSION', '1.0.1' );
define( 'BNN_INTEL_URL', plugin_dir_url( __FILE__ ) );

require_once __DIR__ . '/includes/class-bnn-intel-api.php';
require_once __DIR__ . '/includes/class-bnn-intel-admin.php';
require_once __DIR__ . '/includes/class-bnn-intel-public.php';

BNN_Intel_Admin::init();
BNN_Intel_Public::init();

register_activation_hook( __FILE__, function () {
	BNN_Intel_Public::add_rewrite();
	flush_rewrite_rules();
} );
register_deactivation_hook( __FILE__, 'flush_rewrite_rules' );
